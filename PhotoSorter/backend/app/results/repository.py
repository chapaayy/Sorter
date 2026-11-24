"""Persist isolated runs and atomically publish complete model outputs."""
from pathlib import Path
import json,os,re,shutil
from ..config import RUNS_DIR
from .exporter import MANIFEST_NAME,export
from .copier import copy_photo
from ..storage.categories import Category
from ..storage.temporary import pipeline_directory
from ..storage.filesystem import parent_fd

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
    from server.storage.paths import result_metadata_dir,owned_file
    if model!="megaloc":raise FileNotFoundError(model)
    root=result_metadata_dir(run_id)
    path=owned_file(root/MANIFEST_NAME,root)
    if not path.is_file():raise FileNotFoundError(run_id)
    return path

def save_model(info,model,rows,query_stamps=None,progress=None,on_export_start=None):
    from app.config import APP_STORAGE_ROOT
    from server.storage.paths import run_identity,run_dir,result_media_dir,result_metadata_dir,batch_root,owned_file,result_keys
    if model!="megaloc":raise ValueError("Unsupported result model")
    run_id=info["id"]
    identity=run_identity(run_id)
    if str(identity[0])!=str(info["batch_id"]):raise ValueError("Wrong batch for run")
    keys=result_keys(run_id,identity=identity)
    output=run_dir(run_id,identity=identity)
    media=result_media_dir(run_id,identity=identity)
    metadata=result_metadata_dir(run_id,identity=identity)
    if output.exists() or output.is_symlink():raise FileExistsError('Результат уже опубликован')
    stored=[]
    with pipeline_directory(Category.PROCESSING_STAGING,run_id=run_id) as scratch:
        staging=scratch/"publish"
        staged_media=staging/media.name
        staged_metadata=staging/metadata.name
        staged_media.mkdir(parents=True)
        staged_metadata.mkdir()
        for i,row in enumerate(rows,1):
            source=keys.source(row["query"])
            winner=(row.get("top") or [None])[0]
            sam=winner["label"] if winner else "_Неопределено"
            file=copy_photo(source,staged_media,sam,
                (query_stamps or {}).get(row["query"]) if query_stamps is not None else None)
            published=media/file.relative_to(staged_media)
            stored.append({**row,"assigned_sam":sam,
                "score":row.get("match_score",winner.get("score") if winner else None),
                "reference":winner.get("reference") if winner else None,"copy":str(published)})
            if progress:progress(i,len(rows),source.name)
        if on_export_start:on_export_start()
        export(staged_metadata,stored,run_id=run_id,identity=identity)
        # Publish media and metadata together under the same run tree.
        # Exclusive FIFO run ownership prevents concurrent publication.
        with parent_fd(APP_STORAGE_ROOT,staging.relative_to(APP_STORAGE_ROOT)) as (src_fd,src), \
             parent_fd(APP_STORAGE_ROOT,output.relative_to(APP_STORAGE_ROOT),create=True) as (dst_fd,dst):
            try:os.stat(dst,dir_fd=dst_fd,follow_symlinks=False)
            except FileNotFoundError:pass
            else:raise FileExistsError("Результат уже опубликован")
            os.rename(src,dst,src_dir_fd=src_fd,dst_dir_fd=dst_fd)
            os.fsync(dst_fd)
    return stored

def load_model(run_id,model):
    from server.storage.paths import result_keys
    keys=result_keys(run_id)
    with manifest_path(run_id,model).open("r",encoding="utf-8") as stream:
        rows=[]
        for index,line in enumerate(stream):
            row=json.loads(line)
            if row.pop("index")!=index:raise ValueError("Invalid result row index")
            rows.append(keys.decode(row))
        return rows
