"""Persist in-flight IO leases so cleanup cannot remove files still in use."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from ..database import connect

def start(batch_id, kind):
    token = uuid.uuid4()
    with connect() as db:
        row = db.execute("SELECT delete_state FROM batches WHERE id=%s FOR SHARE", (batch_id,)).fetchone()
        if not row: raise HTTPException(404, "Партия не найдена")
        if row["delete_state"] != "active":
            raise HTTPException(409, "Партия удаляется или уже удалена")
        db.execute("INSERT INTO batch_operations(id,batch_id,kind) VALUES (%s,%s,%s)",
                   (token,batch_id,kind))
    return token

def heartbeat(token):
    with connect() as db:
        count = db.execute("UPDATE batch_operations SET heartbeat_at=now() WHERE id=%s RETURNING id",
                           (token,)).fetchone()
        if not count:
            raise RuntimeError("Operation lease expired")

def finish(token):
    if token:
        with connect() as db:
            db.execute("DELETE FROM batch_operations WHERE id=%s", (token,))
