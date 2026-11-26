"""Side metadata for the existing durable reference import pipeline.

All mutating callers already hold the FIFO publication lock. No physical
storage operation, version rewrite, or model invocation is performed here.
"""
from fastapi import HTTPException


def normalize_import_side(value,portable=False):
    from .reference_sides import normalize_side
    # Portable manifests can preserve exact historical labels. These are SQL
    # metadata only and never interpreted as filesystem paths.
    if portable and value is not None:
        if not 1<=len(value)<=60 or not value.strip() or any(ord(c)<32 or 127<=ord(c)<=159 for c in value):
            raise HTTPException(422,"Некорректная историческая сторона")
        return value
    return normalize_side(value)


def desired_sides(entries):
    requested={}
    for entry in entries:
        side=entry["side"]
        digest=entry["checksum"]
        if not side or not digest:
            continue
        key=(entry["sam"],digest)
        if key in requested and requested[key]!=side:
            raise HTTPException(409,f"Одинаковый образец в разных сторонах: {key[0]}")
        requested[key]=side
    return requested


def validate_existing_sides(db, requested):
    if not requested:
        return
    sams,digests=map(list,zip(*requested))
    rows=db.execute("""
        SELECT m.sam,m.source_hash,p.side
        FROM unnest(%s::text[],%s::text[]) AS selected(sam,digest)
        JOIN reference_version_members m
          ON (m.sam,m.source_hash)=(selected.sam,selected.digest)
        JOIN reference_library_state s ON s.current_version_id=m.version_id
        LEFT JOIN reference_photo_sides p ON p.reference_id=m.reference_id
        WHERE s.id=1
    """,(sams,digests)).fetchall()
    for row in rows:
        side=requested[(row["sam"],row["source_hash"])]
        if row["side"]!=side:
            raise HTTPException(409,f"Конфликт стороны {row['sam']}: "
                f"{row['side'] or 'Без стороны'} → {side}. Существующее назначение сохранено")


def assign_new_sides(db,members,requested):
    rows=[(m["reference_id"],m["sam"],requested[(m["sam"],m["source_hash"])])
          for m in members if (m["sam"],m["source_hash"]) in requested]
    if rows:
        with db.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO reference_photo_sides(reference_id,sam,side)
                VALUES (%s,%s,%s)
            """,rows)


def resolve_conflicts(changes):
    """Explicitly confirmed metadata changes, all-or-nothing under the FIFO lock.

    Bind confirmation to the published photo UUID, construction, hash and
    previously reviewed side. A retry after a lost response is harmless.
    """
    from ..database import connect
    from ..storage import reference_objects
    unique={}
    for change in changes:
        side=normalize_import_side(change.requested_side,getattr(change,'portable',False))
        if side is None:
            raise HTTPException(422,"Выберите назначаемую сторону")
        value=(change.sam,change.sha256,change.size,change.existing_side,side)
        if change.reference_id in unique and unique[change.reference_id]!=value:
            raise HTTPException(422,"Противоречивые решения для одного образца")
        unique[change.reference_id]=value
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        rows=db.execute("""
            SELECT m.reference_id,m.sam,m.source_hash,m.declared_size,m.target_path,p.side
            FROM reference_version_members m
            JOIN reference_library_state s ON s.current_version_id=m.version_id
            JOIN uploads u ON u.id=m.reference_id AND u.sam=m.sam
                AND u.kind='reference' AND u.finalized
            LEFT JOIN reference_photo_sides p ON p.reference_id=m.reference_id
            WHERE s.id=1 AND m.source_kind='staged' AND m.reference_id=ANY(%s)
        """,(list(unique),)).fetchall()
        if len(rows)!=len(unique):
            raise HTTPException(409,"Библиотека изменилась. Повторите проверку образцов")
        updates=[]
        for row in rows:
            sam,digest,size,expected,side=unique[row["reference_id"]]
            if (row["sam"],row["source_hash"],row["declared_size"])!=(sam,digest,size):
                raise HTTPException(409,"Образец изменился. Повторите проверку")
            if row["side"] not in (expected,side):
                raise HTTPException(409,"Сторона изменилась после проверки. Повторите импорт")
            try:
                reference_objects.verify_object(row["target_path"],size,digest=digest)
            except (OSError,ValueError,TypeError) as exc:
                raise HTTPException(409,"Исходный образец недоступен. Повторите проверку") from exc
            if row["side"]!=side:
                updates.append((row["reference_id"],sam,side))
        if updates:
            with db.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO reference_photo_sides(reference_id,sam,side)
                    VALUES (%s,%s,%s) ON CONFLICT(reference_id) DO UPDATE
                    SET sam=excluded.sam,side=excluded.side,updated_at=now()
                """,updates)
    return {"confirmed":len(unique),"updated":len(updates)}
