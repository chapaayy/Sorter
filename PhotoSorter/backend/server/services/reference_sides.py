"""Assign construction sides to published reference IDs without touching MegaLoc.

The shared FIFO claim lock freezes side labels into each claimed FO snapshot.
This metadata update never changes reference bytes, version IDs or embeddings.
"""
from __future__ import annotations
import unicodedata
from fastapi import HTTPException
from app.photos.labels import check_label
from ..database import connect

_FORBIDDEN = '<>:"/\\\\|?*'


def normalize_side(value: str | None) -> str | None:
    if value is None:
        return None
    name = " ".join(value.strip().split())
    if name.casefold().startswith("сторона "):
        name = name[8:].strip()
    if (not name or len(name) > 60 or name in (".", "..") or name.endswith(".")
            or any(ord(c)<32 or c in _FORBIDDEN for c in name) or name.casefold() == "неназначена сторона"):
        raise HTTPException(422, "Название стороны: от 1 до 60 символов, без символов пути")
    return unicodedata.normalize("NFC", name)


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
