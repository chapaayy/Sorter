"""Validate construction keys and manage published construction addresses."""
from __future__ import annotations

from fastapi import HTTPException
from app.photos.construction import CITIES, parse_folder_name
from ..database import connect
import json
import re
from app.photos.construction import parse_key
from app.photos.labels import check_label

_EDIT_LOCK = 723409133


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


def change_address(sam: str, address: str) -> dict:
    try:
        item = parse_folder_name(f"{sam} — {address}")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(%s)",(_EDIT_LOCK,))
        updated = db.execute("""
            UPDATE reference_constructions SET address=%s,updated_at=now()
            WHERE sam=%s RETURNING sam,address
        """,(item.address,item.key)).fetchone()
        if not updated:
            raise HTTPException(404,"Конструкция не найдена")
        current=db.execute("""SELECT current_version_id FROM reference_library_state
            WHERE id=1""").fetchone()
        if current and current["current_version_id"]:
            db.execute("""INSERT INTO reference_library_events(version_id,event_kind,details)
                VALUES (%s,'address_changed',%s::jsonb)""",
                (current["current_version_id"],json.dumps({"sam":updated["sam"]})))
    return {"sam":updated["sam"],"address":updated["address"],
            "name":f"{updated['sam']} — {updated['address']}"}


def create(kind: str, *, city_code: str | None = None,
           number: str | None = None, address: str | None = None,
           name: str | None = None) -> dict:
    """Create an EMPTY catalog entry; photo recognition changes only after FIFO preparation."""
    if kind == "standard":
        try:
            item=parse_folder_name(f"{city_code or ''} {number or ''} — {address or ''}")
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        sam=item.key
        title=item.title
        values=(sam,item.city_code,item.number,item.address,"standard")
    elif kind == "custom":
        proposed=(name or "").strip()
        try:
            canonical=check_label(proposed)
            if canonical!=proposed or re.match(r'^SAM-\\d{4}',proposed,re.I):
                raise ValueError("Некорректное индивидуальное название")
            try:
                parse_key(proposed)
            except ValueError:
                pass
            else:
                raise ValueError("Для кода города и номера используйте обычную конструкцию")
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        sam=proposed
        title=proposed
        values=(sam,None,None,None,"custom")
    else:
        raise HTTPException(422,"Неизвестный тип конструкции")
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(%s)",(_EDIT_LOCK,))
        if db.execute("SELECT 1 FROM reference_constructions WHERE sam=%s",(sam,)).fetchone() or \
           db.execute("SELECT 1 FROM uploads WHERE sam=%s AND kind='reference' LIMIT 1",(sam,)).fetchone():
            raise HTTPException(409,"Конструкция с таким названием уже существует")
        db.execute("""INSERT INTO reference_constructions
            (sam,city_code,construction_number,address,kind)
            VALUES (%s,%s,%s,%s,%s)""",values)
    return {"sam":sam,"display_name":title,"kind":kind,"photos":0,
            "city_code":values[1],"construction_number":values[2],"address":values[3]}
