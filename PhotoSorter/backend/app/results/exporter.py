"""Publish machine-readable per-model score, alternatives, verdict and copy path."""
import csv,json,os,tempfile,threading,time
from pathlib import Path

# Run progress is read by the browser while the worker writes new snapshots.
# On Windows, replacing a file opened for reading can raise WinError 5 or 32.
# Unique temporary files, serialised writes, and bounded retry avoid corrupting
# an existing snapshot or crashing the job on transient file sharing conflicts.
_json_write_lock = threading.Lock()
_REPLACE_RETRY_SECONDS = (0.03, 0.05, 0.08, 0.13, 0.20, 0.30, 0.45, 0.60)


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    with _json_write_lock:
        fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                file.write(payload)
            for attempt in range(len(_REPLACE_RETRY_SECONDS) + 1):
                try:
                    os.replace(temp, path)
                    return
                except PermissionError as exc:
                    if attempt == len(_REPLACE_RETRY_SECONDS) or getattr(exc, 'winerror', None) not in (None, 5, 32, 33):
                        raise
                    time.sleep(_REPLACE_RETRY_SECONDS[attempt])
        finally:
            temp.unlink(missing_ok=True)

def export(model_dir,rows):
    model_dir=Path(model_dir)
    atomic_json(model_dir/'manifest.json',rows)
    # Stage 2 galleries scan this append-free index lazily. Legacy JSON remains identical.
    with (model_dir/'manifest.rows.jsonl').open('w',encoding='utf-8') as stream:
        for index,row in enumerate(rows):
            stream.write(json.dumps({'index':index,**row},ensure_ascii=False,separators=(',',':'))+'\\n')
    with (model_dir/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['query','sam','score','reference','copy','alternative_candidates','verdict','reason','checked_count','group_id','group_size','group_status','individual_sam','individual_top'],delimiter=';')
        writer.writeheader()
        for r in rows:
            writer.writerow({
                'query':r['query'],'sam':r['assigned_sam'],'score':r.get('score'),
                'reference':r.get('reference'),'copy':r.get('copy'),
                'alternative_candidates':json.dumps(r.get('top',[]),ensure_ascii=False),
                'verdict':r.get('verdict'),'reason':r.get('reason'),'checked_count':r.get('checked_count'),
                'group_id':r.get('group_id'),'group_size':r.get('group_size'),
                'group_status':r.get('group_status'),'individual_sam':r.get('individual_sam'),
                'individual_top':json.dumps(r.get('individual_top',[]),ensure_ascii=False)})
