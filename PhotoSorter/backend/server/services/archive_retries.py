"""Compatibility status for old clients; ZIPs are no longer queue tasks."""
from fastapi import HTTPException
from ..database import connect

def archive_status(run_id:str):
    with connect() as db:
        row=db.execute("SELECT status FROM jobs WHERE id=%s",(run_id,)).fetchone()
    if not row:raise HTTPException(404,"Запуск не найден")
    return {"run_id":run_id,"state":"on_demand" if row["status"] in
            ("completed","completed_with_errors") else "unavailable","can_retry":False}

def request(run_id:str):
    archive_status(run_id)
    raise HTTPException(409,"ZIP создаётся только по кнопке скачивания")
