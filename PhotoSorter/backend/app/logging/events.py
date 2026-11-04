"""JSONL events scoped by run and optional model."""
from datetime import datetime,timezone
import json,threading
from pathlib import Path
from ..config import RUNS_DIR
_lock=threading.Lock()
def emit(run_id,level,message,model=None):
    event={'at':datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
           'level':level,'model':model,'message':message}
    file=RUNS_DIR/run_id/'events.jsonl'
    file.parent.mkdir(parents=True,exist_ok=True)
    with _lock:
        with file.open('a',encoding='utf-8') as f: f.write(json.dumps(event,ensure_ascii=False)+'\n')
    return event

def read(run_id,model=None,level=None):
    file=RUNS_DIR/run_id/'events.jsonl'
    if not file.is_file(): return []
    rows=[]
    for line in file.read_text(encoding='utf-8').splitlines():
        try: data=json.loads(line)
        except ValueError: continue
        if model and data.get('model')!=model: continue
        if level and data['level']!=level: continue
        rows.append(data)
    return rows
