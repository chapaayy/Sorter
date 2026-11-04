"""Persist isolated runs and completed model outputs."""
from pathlib import Path
import json,re
from ..config import RUNS_DIR
from .exporter import atomic_json,export
from .copier import copy_photo

def run_path(run_id):
    if not re.fullmatch(r'\d{8}T\d{6}-[a-f0-9]{12}',str(run_id)):
        raise FileNotFoundError('Некорректный идентификатор запуска')
    return RUNS_DIR/run_id

def save_run(info): atomic_json(run_path(info['id'])/'run.json',info)

def load_run(run_id):
    file=run_path(run_id)/'run.json'
    if not file.is_file(): raise FileNotFoundError(run_id)
    return json.loads(file.read_text('utf-8'))

def list_runs():
    rows=[]
    if not RUNS_DIR.is_dir(): return rows
    for folder in RUNS_DIR.iterdir():
        try: rows.append(load_run(folder.name))
        except (OSError,ValueError): pass
    return sorted(rows,key=lambda x:x.get('started_at',''),reverse=True)

def save_model(info,model,rows,query_stamps=None,progress=None,on_export_start=None):
    output=Path(info['output'])/info['id']/model
    stored=[]
    for i,row in enumerate(rows,1):
        winner=(row.get('top') or [None])[0]
        sam=winner['label'] if winner else '_Неопределено'
        copy=copy_photo(row['query'],output,sam,
                        (query_stamps or {}).get(row['query']) if query_stamps is not None else None)
        stored.append({**row,'assigned_sam':sam,'score':winner.get('score') if winner else None,
                       'reference':winner.get('reference') if winner else None,'copy':str(copy)})
        if progress: progress(i,len(rows),Path(row['query']).name)
    if on_export_start: on_export_start()
    export(output,stored)
    # Store stable pointer to the actual run output folder, not large photo bytes.
    index=run_path(info['id'])/'models'
    index.mkdir(parents=True,exist_ok=True)
    atomic_json(index/f'{model}.json',{'model':model,'path':str(output/'manifest.json'),'count':len(rows)})
    return stored

def load_model(run_id,model):
    if not re.fullmatch(r'[a-z0-9-]+',str(model)):
        raise FileNotFoundError('Некорректная модель')
    path=run_path(run_id)/'models'/f'{model}.json'
    if not path.is_file(): raise FileNotFoundError(model)
    index=json.loads(path.read_text('utf-8'))
    return json.loads(Path(index['path']).read_text('utf-8'))
