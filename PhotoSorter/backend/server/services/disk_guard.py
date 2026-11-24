"""Existing filesystem floor plus optional stricter owner reserve."""
from __future__ import annotations
import os
from pathlib import Path
from fastapi import HTTPException
from app import config
# Compatibility with existing callers; admission itself uses the canonical app mount.
DATA_DIR=config.DATA_DIR

def stat(path=None):
    fs=os.statvfs(path or config.APP_STORAGE_ROOT)
    return fs.f_frsize*fs.f_blocks,fs.f_frsize*fs.f_bavail

def reserve(total_bytes,*,configured=None):
    env=os.environ.get("PHOTOSORTER_MIN_FREE_BYTES")
    baseline=max(0,int(env)) if env else min(12*1024**3,max(256*1024**2,int(total_bytes*.06)))
    return max(baseline,configured or 0)

def check_admission(bytes_needed,*,path=None):
    from .. import database
    root=path or config.APP_STORAGE_ROOT
    if database.DB_URL:
        from ..storage import admission
        with database.connect() as db:
            admission.lock(db)
            admission.admit(db,int(bytes_needed),path=root)
            total,available=stat(root)
            minimum=reserve(total,configured=admission.policy(db)["disk_reserve_bytes"])
    else:
        total,available=stat(root);minimum=reserve(total)
        if available-int(bytes_needed)<minimum:
            raise HTTPException(507,"Недостаточно места: сохранён резерв для базы и системы")
    return {"total":total,"available":available,"reserved":minimum}
