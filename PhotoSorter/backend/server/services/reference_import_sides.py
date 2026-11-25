"""Side metadata for the existing durable reference import pipeline.

All mutating callers already hold the FIFO publication lock. No physical
storage operation, version rewrite, or model invocation is performed here.
"""
from fastapi import HTTPException


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
