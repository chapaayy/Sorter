"""Bounded single-directory log writer; no duplicate stdout sink."""
import fcntl
import json
import os
import re
import stat
from datetime import datetime,timezone
from pathlib import Path
from app.storage.categories import LOG_BUDGETS_MIB
from app.storage.filesystem import directory_fd

SERVICES=("api","worker","cleanup","thumbnail","models","updater","audit")
def redact(message):
    text=str(message)
    for name in ("ADMIN_PASSWORD","POSTGRES_PASSWORD","DATABASE_URL"):
        value=os.environ.get(name)
        if value:text=text.replace(value,"[REDACTED]")
    text=re.sub(r"(?i)(?:postgres(?:ql)?|https?)://[^\s/]+:[^\s/@]+@","[REDACTED]@",text)
    text=re.sub(r"(?i)(authorization|cookie|set-cookie|password|passwd|token|api[_-]?key)\s*[:=]\s*[^\r\n]+",r"\1=[REDACTED]",text)
    text=re.sub(r"(?i)Bearer\s+[^\s]+","Bearer [REDACTED]",text)
    text=re.sub(r"\?[^\s\"']+","?[REDACTED]",text)
    return text[:4096]

def write_record(directory,service,message,*,segment_bytes=None,segments=5):
    if service not in SERVICES:raise ValueError("Invalid log service")
    directory=Path(directory)
    if not directory.is_dir():return False
    cap=segment_bytes or LOG_BUDGETS_MIB[service]*1024*1024//segments
    payload=(json.dumps({"at":datetime.now(timezone.utc).isoformat(),"message":redact(message)},ensure_ascii=False)+"\n").encode()
    if len(payload)>cap:payload=b'{"message":"Oversize log record omitted"}\n'
    with directory_fd(directory) as fd:
        fcntl.flock(fd,fcntl.LOCK_EX)
        name="service.jsonl"
        try:
            info=os.stat(name,dir_fd=fd,follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):raise ValueError("Unsafe log target")
            rotate=info.st_size+len(payload)>cap
        except FileNotFoundError:rotate=False
        if rotate:
            for i in range(segments-1,0,-1):
                source=name if i==1 else name+"."+str(i-1)
                try:os.replace(source,name+"."+str(i),src_dir_fd=fd,dst_dir_fd=fd)
                except FileNotFoundError:pass
        handle=os.open(name,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(handle).st_mode):raise ValueError("Invalid log")
            os.write(handle,payload)
        finally:os.close(handle)
    return True

def log(service,message):
    return write_record(Path(os.environ.get("MAP_LOG_ROOT","/logs"))/service,service,message)
