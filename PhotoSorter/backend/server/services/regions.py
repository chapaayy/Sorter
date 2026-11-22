"""Registry of region codes and run-scoped reference selection.

Legacy runs use all references (selected_regions=None). Individual constructions
are global: they are not tied to any city code and are always available.
"""
from __future__ import annotations
import re
from fastapi import HTTPException
from app.photos.construction import parse_key
from ..database import connect

_CODE=re.compile(r"^[A-Z]{2,5}$")
_LOCK=723409133

def validate_code(value: str) -> str:
    if not isinstance(value,str) or not _CODE.fullmatch(value):
        raise HTTPException(422,"Код региона: 2–5 заглавных латинских букв")
    return value

def list_all():
    with connect() as db:
        rows=db.execute("""SELECT r.code,
          (SELECT count(*) FROM reference_constructions c
           WHERE c.kind='standard' AND c.city_code=r.code) AS constructions
          FROM reference_regions r ORDER BY r.code""").fetchall()
    return {"regions":[{"code":r["code"],"constructions":r["constructions"]} for r in rows]}

def register(code: str):
    code=validate_code(code)
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(%s)",(_LOCK,))
        db.execute("INSERT INTO reference_regions(code) VALUES (%s) ON CONFLICT DO NOTHING",(code,))
    return {"code":code}

def ensure_registered(db,codes: list[str]):
    if not codes:return
    known={row["code"] for row in db.execute(
        "SELECT code FROM reference_regions WHERE code=ANY(%s)",(list(set(codes)),)).fetchall()}
    missing=sorted(set(codes)-known)
    if missing:raise HTTPException(422,"Сначала добавьте регионы: "+", ".join(missing))

def selected(db,value: list[str]|None):
    if value is None:return None  # legacy clients & jobs
    if not isinstance(value,list) or not 1<=len(value)<=100:
        raise HTTPException(422,"Выберите от 1 до 100 регионов")
    codes=sorted(set(validate_code(x) for x in value))
    ensure_registered(db,codes)
    return codes

def region_for(sam: str) -> str|None:
    try:return parse_key(sam)[0]
    except ValueError:return None

def filter_members(members: list[dict],codes: list[str]|None):
    if codes is None:return members
    allowed=set(codes)
    return [member for member in members
        if (region_for(member["sam"]) in allowed or region_for(member["sam"]) is None)]
