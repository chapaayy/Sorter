"""Validate and explicitly restore catalog metadata from a portable archive."""
from fastapi import HTTPException
from ..database import connect
from . import construction_catalog,regions

def inspect(constructions,*,create=False):
    desired={}
    for entry in constructions:
        item=construction_catalog.describe(entry.kind,city_code=entry.city_code,
            number=entry.number,address=entry.address,name=entry.sam)
        if (item["sam"]!=entry.sam or item["city_code"]!=entry.city_code
            or item["construction_number"]!=entry.number or item["address"]!=entry.address
            or entry.sam in desired):
            raise HTTPException(422,"Некорректная или повторная конструкция в манифесте")
        desired[entry.sam]=item
    if not desired:
        raise HTTPException(422,"Пустой каталог манифеста")
    with connect() as db:
        if create:
            db.execute("SELECT pg_advisory_xact_lock(723409133)")
        existing={r["sam"]:r for r in db.execute("""
            SELECT c.sam,c.kind,c.city_code,c.construction_number,c.address,
              (SELECT count(*) FROM uploads u WHERE u.sam=c.sam AND u.kind='reference' AND u.finalized) AS photos
            FROM reference_constructions c WHERE c.sam=ANY(%s)
        """,(list(desired),)).fetchall()}
        known={r["code"] for r in db.execute("SELECT code FROM reference_regions").fetchall()}
        missing=sorted({r["city_code"] for r in desired.values() if r["city_code"]}-known)
        errors=[]
        entries=[]
        for sam,item in desired.items():
            row=existing.get(sam)
            if row and any(row[k]!=item[k] for k in ("kind","city_code","construction_number","address")):
                errors.append({"folder":item["display_name"],"reason":"Метаданные конструкции отличаются от сохранённых"})
            entries.append({"sam":sam,"name":item["display_name"],"address":item["address"] or "",
                "city_code":item["city_code"] or "","number":item["construction_number"] or "",
                "existing":row is not None,"photos":row["photos"] if row else 0})
        if not create:
            return {"entries":entries,"errors":errors,"new_regions":missing}
        if errors:
            raise HTTPException(409,errors[0]["reason"]+": "+errors[0]["folder"])
        regions.ensure_registered(db,missing)
        additions=[(v["sam"],v["city_code"],v["construction_number"],v["address"],v["kind"])
                   for k,v in desired.items() if k not in existing]
        if additions:
            with db.cursor() as cursor:
                cursor.executemany("""INSERT INTO reference_constructions
                    (sam,city_code,construction_number,address,kind)
                    VALUES (%s,%s,%s,%s,%s)""",additions)
        return {"created":len(additions)}
