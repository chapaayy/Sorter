"""Reserve filesystem space for PostgreSQL/WAL and running operations."""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import HTTPException
from app.config import DATA_DIR

def stat(path:Path=DATA_DIR):
    fs=os.statvfs(path)
    total=fs.f_frsize*fs.f_blocks
    return total,fs.f_frsize*fs.f_bavail

def reserve(total_bytes):
    configured=os.environ.get("PHOTOSORTER_MIN_FREE_BYTES")
    if configured:return max(0,int(configured))
    return min(12*1024**3,max(256*1024**2,int(total_bytes*.06)))

def check_admission(bytes_needed):
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    total,available=stat(DATA_DIR)
    if available-int(bytes_needed)<reserve(total):
        raise HTTPException(507,"Недостаточно места: сохранён резерв для базы и системы")
    return {"total":total,"available":available,"reserved":reserve(total)}
