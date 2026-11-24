"""Scan published results with constant memory; preserve full legacy JSON endpoint."""
from __future__ import annotations
import base64,json,re
from pathlib import Path
from fastapi import HTTPException
from app.config import DATA_DIR
from app.results.repository import manifest_path

RUN_ID=re.compile(r"\d{8}T\d{6}-[a-f0-9]{12}\Z")

def _cursor(offset,selector):
    obj={"pos":offset,"sel":selector}
    return base64.urlsafe_b64encode(json.dumps(obj,separators=(",",":")).encode()).decode().rstrip("=")

def _parse(cursor,selector,file_size):
    if not cursor:return 0
    try:
        if len(cursor)>400:raise ValueError("Cursor too long")
        value=json.loads(base64.urlsafe_b64decode(cursor+"="*(-len(cursor)%4)))
        offset=int(value["pos"])
        if value["sel"]!=selector or offset<0 or offset>file_size:raise ValueError("Invalid cursor")
        return offset
    except (ValueError,TypeError,KeyError) as exc:
        raise HTTPException(422,"Неверный курсор результата") from exc

def _manifest(run_id):
    if not RUN_ID.fullmatch(run_id):raise HTTPException(404,"Запуск не найден")
    try:return manifest_path(run_id)
    except (OSError,ValueError):raise HTTPException(404,"Результат не найден")

def iter_rows(run_id):
    with _manifest(run_id).open("r",encoding="utf-8") as stream:
        for line in stream:yield json.loads(line)

def page(run_id,*,sam=None,group=None,cursor=None,limit=60):
    if not 1<=limit<=200:raise HTTPException(422,"Неверный лимит")
    if not RUN_ID.fullmatch(run_id):raise HTTPException(404,"Запуск не найден")
    selector={"sam":sam or "","group":group or ""}
    file=_manifest(run_id)
    matches=[]
    next_cursor=None
    with file.open('rb') as stream:
        offset=_parse(cursor,selector,file.stat().st_size)
        if offset:
            stream.seek(offset-1)
            if stream.read(1)!=b"\n":raise HTTPException(422,"Неверный курсор результата")
        stream.seek(offset)
        while len(matches)<=limit:
            start=stream.tell()
            line=stream.readline()
            if not line:break
            row=json.loads(line)
            if sam is not None and row.get("assigned_sam")!=sam:continue
            if group is not None and row.get("group_id")!=group:continue
            matches.append(row)
            if len(matches)>limit:
                next_cursor=_cursor(start,selector)
                break
    return {"rows":matches[:limit],"next_cursor":next_cursor}

def counts(run_id):
    sam={}
    groups={}
    for row in iter_rows(run_id):
        label=row.get("assigned_sam") or "_Неопределено"
        sam[label]=sam.get(label,0)+1
        group=row.get("group_id")
        if group:groups[group]=groups.get(group,0)+1
    return {"sam":sam,"groups":groups}
