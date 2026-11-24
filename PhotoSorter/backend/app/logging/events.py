"""Bounded per-run JSONL rotation and streaming cursor/page reads."""
from __future__ import annotations
import base64,json,os,re,threading,fcntl
from contextlib import contextmanager
from collections import deque
from datetime import datetime,timezone
from pathlib import Path
from ..config import APP_STORAGE_ROOT
from ..storage.categories import LOG_BUDGETS_MIB,RUN_LOG_BUDGET_MIB
from .service import redact
RUNS_DIR=Path(os.environ.get('MAP_LOG_ROOT',str(APP_STORAGE_ROOT.parent/'logs')))/'processing'

RUN_RE=re.compile(r"\d{8}T\d{6}-[a-f0-9]{12}\Z")
SEGMENT_BYTES=RUN_LOG_BUDGET_MIB*1024*1024//5
SEGMENTS=5  # 4 old + active, up to 20 MiB/run
TOTAL_BYTES=LOG_BUDGETS_MIB['processing']*1024*1024
MAX_MESSAGE=4096
_lock=threading.Lock()
_emits=0

def _runpath(run_id):
    if not RUN_RE.fullmatch(str(run_id)):raise ValueError("Invalid run ID")
    return RUNS_DIR/str(run_id)

def _files(run_id):
    root=_runpath(run_id)
    # Chronological order; rotated numbering counts down toward newest.
    return [root/f"events.jsonl.{i}" for i in range(SEGMENTS-1,0,-1)]+[
        root/"events.jsonl"]

def _rotate(active):
    oldest=active.with_name(f"{active.name}.{SEGMENTS-1}")
    oldest.unlink(missing_ok=True)
    for i in range(SEGMENTS-2,0,-1):
        prev=active.with_name(f"{active.name}.{i}")
        if prev.exists():prev.replace(active.with_name(f"{active.name}.{i+1}"))
    if active.exists():active.replace(active.with_name(f"{active.name}.1"))

@contextmanager
def journal_lock():
    RUNS_DIR.mkdir(parents=True,exist_ok=True)
    fd=os.open(RUNS_DIR,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        yield
    finally:os.close(fd)

def _budget(terminal=()):
    """Limit all application run event bytes, never user photos or references."""
    files=[f for f in RUNS_DIR.glob("*/events.jsonl*")
           if f.is_file() and not f.is_symlink() and
           (re.fullmatch(r"events\.jsonl\.[1-4]",f.name) or (f.name=="events.jsonl" and f.parent.name in terminal))]
    usage=sum(f.stat().st_size for f in RUNS_DIR.glob("*/events.jsonl*") if f.is_file() and not f.is_symlink())
    if usage<=TOTAL_BYTES:return
    for item in sorted(files,key=lambda f:f.stat().st_mtime_ns):
        if usage<=TOTAL_BYTES:break
        size=item.stat().st_size
        item.unlink(missing_ok=True)
        usage-=size

def emit(run_id,level,message,model=None,source=None):
    global _emits
    event={"at":datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "level":str(level).upper(),"model":model,
        "source":source or ("MegaLoc" if model else "API"),
        "message":redact(message)[:MAX_MESSAGE]}
    path=_runpath(run_id)/"events.jsonl"
    line=json.dumps(event,ensure_ascii=False,separators=(",",":"))+"\n"
    payload=line.encode("utf-8")
    if len(payload)>SEGMENT_BYTES:raise ValueError("One log record exceeds segment cap")
    with _lock,journal_lock():
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.stat().st_size+len(payload)>SEGMENT_BYTES:
            _rotate(path)
        with path.open("ab") as stream:stream.write(payload)
        _emits+=1
        if _emits%32==0:_budget()
    return event

def prune_terminal(terminal):
    # Only authoritative DB-terminal runs are eligible for active-file deletion.
    with _lock,journal_lock():
        _budget(set(terminal))

def _accept(row,model=None,level=None,source=None,search=None):
    if model and row.get("model")!=model:return False
    if level and row.get("level")!=level.upper():return False
    if source and row.get("source")!=source:return False
    if search and search.lower() not in str(row.get("message","")).lower():return False
    return True

def read(run_id,model=None,level=None,limit=250,source=None,search=None):
    """Compatibility tail: bounded memory, most recent rows for the old polling UI."""
    if not 1<=limit<=1000:raise ValueError("Invalid limit")
    events=deque(maxlen=limit)
    for f in _files(run_id):
        if not f.is_file():continue
        with f.open("rb") as stream:
            for line in stream:
                try:row=json.loads(line)
                except (ValueError,UnicodeDecodeError):continue
                if _accept(row,model,level,source,search):events.append(row)
    return list(events)

def _encode(name,offset):
    raw=json.dumps({"name":name,"offset":offset},separators=(",",":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")

def _decode(value):
    if not value:return None
    try:
        if len(value)>400:raise ValueError("long cursor")
        payload=json.loads(base64.urlsafe_b64decode(value+"="*(-len(value)%4)))
        name,offset=payload["name"],int(payload["offset"])
        if name not in [p.name for p in _files("20260101T000000-abcdef123456")] or offset<0:
            raise ValueError("Invalid cursor")
        return name,offset
    except (KeyError,ValueError,TypeError,UnicodeDecodeError):
        raise ValueError("Invalid log cursor")

def page(run_id,*,cursor=None,limit=200,model=None,level=None,source=None,search=None):
    if not 1<=limit<=500:raise ValueError("Invalid limit")
    files=_files(run_id)
    position=_decode(cursor)
    if position and not (_runpath(run_id)/position[0]).is_file():
        raise ValueError("Rotated cursor no longer exists")
    results=[]
    started=position is None
    for f in files:
        if not f.is_file():continue
        if not started:
            if f.name!=position[0]:continue
            started=True
        with f.open("rb") as stream:
            if position and f.name==position[0]:
                if position[1]>f.stat().st_size:raise ValueError("Stale log cursor")
                stream.seek(position[1])
            for line in stream:
                offset=stream.tell()
                try:row=json.loads(line)
                except (ValueError,UnicodeDecodeError):continue
                if _accept(row,model,level,source,search):
                    results.append(row)
                    if len(results)>=limit:
                        return {"events":results,"next_cursor":_encode(f.name,offset)}
    return {"events":results,"next_cursor":None}

def usage():
    files=[f for f in RUNS_DIR.glob("*/events.jsonl*") if f.is_file() and not f.is_symlink()]
    return {"bytes":sum(f.stat().st_size for f in files),
            "budget_bytes":TOTAL_BYTES,"run_budget_bytes":SEGMENT_BYTES*SEGMENTS}

def tail(run_id,*,limit=200,model=None,level=None,source=None,search=None):
    """Return recent bounded events with a cursor AFTER the currently published tail."""
    rows=read(run_id,model=model,level=level,source=source,search=search,limit=limit)
    files=[f for f in _files(run_id) if f.is_file()]
    if not files:return {"events":rows,"next_cursor":None}
    newest=files[-1]
    return {"events":rows,"next_cursor":_encode(newest.name,newest.stat().st_size)}
