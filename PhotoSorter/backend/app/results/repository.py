"""Persist isolated runs and atomically publish complete model outputs."""
from pathlib import Path
import json,os,re,shutil
from ..config import RUNS_DIR
from .exporter import MANIFEST_NAME,export
from .copier import copy_photo

def run_path(run_id):
    if not re.fullmatch(r'\d{8}T\d{6}-[a-f0-9]{12}',str(run_id)):
        raise FileNotFoundError('Некорректный идентификатор запуска')
    return RUNS_DIR/run_id

def load_run(run_id):
    from server.database import connect
    from server.db.repositories.job_status import decorated
    run_path(run_id)
    with connect() as db:
        row=db.execute("SELECT id,snapshot,status,created_at,started_at,finished_at FROM jobs WHERE id=%s",(run_id,)).fetchone()
        if not row:raise FileNotFoundError(run_id)
        return decorated(db,row)

def manifest_path(run_id,model="megaloc"):
    from server.storage.paths import run_dir,owned_file
    if model!="megaloc":raise FileNotFoundError(model)
    root=run_dir(run_id)
    path=owned_file(root/model/MANIFEST_NAME,root)
    if not path.is_file():raise FileNotFoundError(run_id)
    return path

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
            stored.append({**row,'assigned_sam':sam,
                'score':row.get('match_score',winner.get('score') if winner else None),
                'reference':winner.get('reference') if winner else None,'copy':str(published)})
            if progress:progress(i,len(rows),Path(row['query']).name)
        if on_export_start:on_export_start()
        export(staging,stored)
        os.rename(staging,output)
    except Exception:
        if staging.exists():shutil.rmtree(staging)
        raise
    return stored

def load_model(run_id,model):
    with manifest_path(run_id,model).open("r",encoding="utf-8") as stream:
        rows=[]
        for index,line in enumerate(stream):
            row=json.loads(line)
            if row.pop("index")!=index:raise ValueError("Invalid result row index")
            rows.append(row)
        return rows
