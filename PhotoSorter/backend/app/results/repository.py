"""Persist isolated runs and atomically publish complete model outputs."""
from pathlib import Path
import json,os,re,shutil
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
    if not RUNS_DIR.is_dir():return rows
    for folder in RUNS_DIR.iterdir():
        try:rows.append(load_run(folder.name))
        except (OSError,ValueError):pass
    return sorted(rows,key=lambda x:x.get('started_at',''),reverse=True)

def save_model(info,model,rows,query_stamps=None,progress=None,on_export_start=None):
    output=Path(info['output'])/info['id']/model
    staging=output.parent/f'.{model}.building'
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise FileExistsError('Результат уже опубликован')
    if staging.is_symlink():raise ValueError('Недопустимый временный каталог')
    if staging.exists():shutil.rmtree(staging)
    stored=[]
    try:
        for i,row in enumerate(rows,1):
            winner=(row.get('top') or [None])[0]
            sam=winner['label'] if winner else '_Неопределено'
            file=copy_photo(row['query'],staging,sam,
                (query_stamps or {}).get(row['query']) if query_stamps is not None else None)
            # Manifests always reference published paths, not staging ones.
            published=output/file.relative_to(staging)
            stored.append({**row,'assigned_sam':sam,'score':winner.get('score') if winner else None,
                'reference':winner.get('reference') if winner else None,'copy':str(published)})
            if progress:progress(i,len(rows),Path(row['query']).name)
        if on_export_start:on_export_start()
        export(staging,stored)
        os.rename(staging,output)
    except Exception:
        if staging.exists():shutil.rmtree(staging)
        raise
    index=run_path(info['id'])/'models'
    index.mkdir(parents=True,exist_ok=True)
    atomic_json(index/f'{model}.json',{'model':model,
        'path':str(output/'manifest.json'),'count':len(rows)})
    return stored

def load_model(run_id,model):
    if not re.fullmatch(r'[a-z0-9-]+',str(model)):
        raise FileNotFoundError('Некорректная модель')
    path=run_path(run_id)/'models'/f'{model}.json'
    if not path.is_file():raise FileNotFoundError(model)
    index=json.loads(path.read_text('utf-8'))
    return json.loads(Path(index['path']).read_text('utf-8'))
