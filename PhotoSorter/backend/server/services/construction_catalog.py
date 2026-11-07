"""Server-authoritative construction names and additive reference registry.

Existing SAM-xxxx references remain untouched for historical result compatibility.
New mass imports always use strict CITY NUMBER — ADDRESS names.
"""
from __future__ import annotations

from fastapi import HTTPException
from app.photos.construction import CITIES, parse_folder_name, parse_key
from app.photos.labels import check_label
from ..database import connect

_EDIT_LOCK = 723409133


def _active_jobs(db):
    return (db.execute(
        "SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1"
    ).fetchone() is not None or
        db.execute("""SELECT 1 FROM work_queue WHERE kind='reference_preparation'
          AND state IN ('queued','running','failed','interrupted','blocked') LIMIT 1""").fetchone() is not None)


def preview(folders: list[str]) -> dict:
    if not folders or len(folders) > 5000:
        raise HTTPException(422, "Выберите от 1 до 5000 папок конструкций")
    unique: dict[str, object] = {}
    errors = []
    for folder in folders:
        try:
            item = parse_folder_name(folder)
            previous = unique.get(item.key)
            if previous and previous.address != item.address:
                errors.append({"folder": folder, "reason":
                               f"Для {item.key} указаны разные адреса в одном пакете"})
            else:
                unique[item.key] = item
        except ValueError as exc:
            errors.append({"folder": folder, "reason": str(exc)})
    entries = []
    if unique:
        with connect() as db:
            rows = db.execute("""
                SELECT c.sam,c.address,
                       (SELECT count(*) FROM uploads u
                        WHERE u.kind='reference' AND u.finalized AND u.sam=c.sam) AS photos
                FROM reference_constructions c WHERE c.sam=ANY(%s)
            """, (list(unique),)).fetchall()
        existing = {row["sam"]: row for row in rows}
        for item in unique.values():
            row = existing.get(item.key)
            if row and row["address"] != item.address:
                errors.append({"folder": item.title, "reason":
                               f"Адрес отличается от сохранённого: {row['address']}. "
                               "Измените адрес конструкции отдельно или исправьте папку."})
            entries.append({"sam":item.key,"name":item.title,"address":item.address,
                            "city_code":item.city_code,"number":item.number,
                            "existing":bool(row),"photos":row["photos"] if row else 0})
    return {"entries":entries,"errors":errors,"cities":CITIES}


def ensure_upload(db, sam: str, address: str | None) -> str:
    """Called inside locked upload-creation transaction, never modifies an existing address."""
    if address is not None:
        item = parse_folder_name(f"{sam} — {address}")
        if item.key != sam:
            raise ValueError("Неверный идентификатор конструкции")
        db.execute("""
            INSERT INTO reference_constructions(sam,city_code,construction_number,address)
            VALUES (%s,%s,%s,%s) ON CONFLICT(sam) DO NOTHING
        """, (sam,item.city_code,item.number,item.address))
        existing = db.execute(
            "SELECT address FROM reference_constructions WHERE sam=%s FOR UPDATE",
            (sam,)
        ).fetchone()
        if existing["address"] != address:
            raise HTTPException(409,
                f"У конструкции {sam} другой адрес: {existing['address']}")
        return sam

    # Adding individual photos requires an existing construction; never infer
    # the address from the filename and never create anonymous constructions.
    try:
        parse_key(sam)
    except ValueError:
        try:
            old = check_label(sam)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        if old != sam:
            raise HTTPException(422,"Укажите существующий идентификатор конструкции")
        row = db.execute(
            "SELECT 1 FROM uploads WHERE kind='reference' AND finalized AND sam=%s LIMIT 1",
            (sam,)
        ).fetchone()
        if not row:
            raise HTTPException(422,"Сначала импортируйте папку конструкции с адресом")
        return sam
    row = db.execute("SELECT 1 FROM reference_constructions WHERE sam=%s",(sam,)).fetchone()
    if not row:
        raise HTTPException(422,"Сначала импортируйте папку конструкции с адресом")
    return sam


def change_address(sam: str, address: str) -> dict:
    try:
        item = parse_folder_name(f"{sam} — {address}")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(%s)",(_EDIT_LOCK,))
        if _active_jobs(db):
            raise HTTPException(409,"Изменение Образцов недоступно во время сортировки")
        updated = db.execute("""
            UPDATE reference_constructions SET address=%s,updated_at=now()
            WHERE sam=%s RETURNING sam,address
        """,(item.address,item.key)).fetchone()
        if not updated:
            raise HTTPException(404,"Конструкция не найдена")
    return {"sam":updated["sam"],"address":updated["address"],
            "name":f"{updated['sam']} — {updated['address']}"}
