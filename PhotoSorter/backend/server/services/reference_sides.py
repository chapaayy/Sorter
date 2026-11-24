"""Assign construction sides to published reference IDs without touching MegaLoc.

The shared FIFO claim lock freezes side labels into each claimed FO snapshot.
This metadata update never changes reference bytes, version IDs or embeddings.
"""
from __future__ import annotations
from fastapi import HTTPException
from app.photos.labels import check_label
from ..database import connect

# Latin letters only. Cyrillic labels from earlier versions are normalized
# by migration 0035; existing unrelated names remain untouched until reassigned.
SIDES = frozenset(f"{letter}{suffix}" for letter in ("A", "B")
                  for suffix in ("", "1", "2", "3"))


def normalize_side(value: str | None) -> str | None:
    if value is None:
        return None
    side = value.strip().upper()
    if side not in SIDES:
        raise HTTPException(422, "Допустимые стороны: A, A1–A3, B, B1–B3")
    return side


def active_sides(db, ids: list) -> dict[str, str]:
    if not ids:
        return {}
    rows = db.execute("SELECT reference_id,side FROM reference_photo_sides WHERE reference_id=ANY(%s)",
                      (ids,)).fetchall()
    return {str(row["reference_id"]): row["side"] for row in rows}


def assign(sam: str, identifiers: list, side: str | None) -> dict:
    try:
        if check_label(sam) != sam:
            raise ValueError("Некорректная конструкция")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    side = normalize_side(side)
    ids = list(dict.fromkeys(identifiers))
    if not 1 <= len(ids) <= 500:
        raise HTTPException(422, "Выберите от 1 до 500 образцов")
    with connect() as db:
        # Same lock used when a FO job pins reference metadata.
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        rows = db.execute("""SELECT u.id FROM uploads u
            JOIN reference_version_members m ON m.reference_id=u.id
            JOIN reference_library_state s ON s.current_version_id=m.version_id
            WHERE u.id=ANY(%s) AND u.sam=%s AND u.kind='reference' AND u.finalized
              AND m.sam=u.sam""", (ids, sam)).fetchall()
        if len(rows) != len(ids):
            raise HTTPException(409, "Некоторые образцы уже удалены или относятся к другой конструкции")
        if side is None:
            db.execute("DELETE FROM reference_photo_sides WHERE reference_id=ANY(%s)", (ids,))
        else:
            existing = db.execute("""SELECT side FROM reference_photo_sides
                WHERE sam=%s AND lower(side)=lower(%s) LIMIT 1""", (sam, side)).fetchone()
            if existing:
                side = existing["side"]
            with db.cursor() as cursor:
                cursor.executemany("""INSERT INTO reference_photo_sides(reference_id,sam,side)
                    VALUES (%s,%s,%s) ON CONFLICT(reference_id)
                    DO UPDATE SET sam=excluded.sam,side=excluded.side,updated_at=now()""",
                    [(ident,sam,side) for ident in ids])
    return {"updated":len(ids),"side":side}


def export_snapshot() -> dict:
    """Portable metadata only; one SQL statement gives a consistent library view.

    The construction label and content digest survive re-import with new UUIDs.
    Preserve unassigned and historical nonstandard labels as-is. No file reads,
    mutations, archive creation, or persistent export files.
    """
    from datetime import datetime, timezone

    with connect() as db:
        rows = db.execute("""
            SELECT v.version_number, v.manifest_digest, m.reference_id,
                   m.sam, m.filename, m.source_hash, m.declared_size,
                   c.kind, c.city_code, c.construction_number, c.address, s.side
            FROM reference_library_state state
            JOIN reference_library_versions v ON v.id=state.current_version_id
            LEFT JOIN reference_version_members m ON m.version_id=v.id
            LEFT JOIN reference_constructions c ON c.sam=m.sam
            LEFT JOIN reference_photo_sides s ON s.reference_id=m.reference_id
            WHERE state.id=1
            ORDER BY m.sam, m.reference_id
        """).fetchall()
    if not rows:
        raise HTTPException(409, "Библиотека образцов ещё не инициализирована")
    photos = [{
        "reference_id": str(row["reference_id"]),
        "sam": row["sam"],
        "filename": row["filename"],
        "sha256": row["source_hash"],
        "size": row["declared_size"],
        "side": row["side"],
        "construction": {
            "kind": row["kind"],
            "city_code": row["city_code"],
            "number": row["construction_number"],
            "address": row["address"],
        },
    } for row in rows if row["reference_id"] is not None]
    assigned = sum(photo["side"] is not None for photo in photos)
    return {
        "schema": "map-reference-sides-v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "library_version": rows[0]["version_number"],
        "manifest_digest": rows[0]["manifest_digest"],
        "total": len(photos),
        "assigned": assigned,
        "unassigned": len(photos) - assigned,
        "photos": photos,
    }
