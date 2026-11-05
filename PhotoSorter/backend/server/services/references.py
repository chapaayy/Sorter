"""Explicit SAM management. PostgreSQL validates ownership; links precede row update."""
from __future__ import annotations
import errno,os,re,shutil
from pathlib import Path
from fastapi import HTTPException
from app.config import DATA_DIR
from ..storage.paths import run_dir
from app.photos.labels import check_label
from app.system.model_store import signature
from ..database import connect
from ..storage.paths import owned_file,owned_directory

REFS=DATA_DIR/"references"

def sam_id(value):
    try:label=check_label(value)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    if not re.fullmatch(r"SAM-\d{4}(?:-[A-Za-zА-Яа-я0-9]{1,8}){0,2}",label):
        raise HTTPException(422,"Ожидался идентификатор SAM-xxxx")
    return label

def _editable(db,source):
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone():
        raise HTTPException(409,"Образцы заблокированы на время обработки")
    if db.execute("""SELECT 1 FROM uploads WHERE kind='reference' AND sam=%s
                   AND NOT finalized LIMIT 1""",(source,)).fetchone():
        raise HTTPException(409,"Дождитесь окончания загрузок этой SAM")

def _historical_reference_guard(db,sam):
    """Fail closed if a published run still names this SAM in its immutable manifest.

    Rename/delete must not silently invalidate a historic score/reference path.
    No modification to MegaLoc output manifests or model weights.
    """
    rows=db.execute("""SELECT id FROM jobs
        WHERE status IN ('completed','completed_with_errors')""").fetchall()
    marker=sam.encode('utf-8')
    for row in rows:
        try:
            manifest=run_dir(row["id"],DATA_DIR/"outputs")/"megaloc"/"manifest.json"
        except ValueError:
            raise HTTPException(409,"Исторический запуск с неверным ID; SAM не изменена")
        if manifest.is_symlink():
            raise HTTPException(409,"Недоверенный исторический manifest; SAM не изменена")
        if not manifest.is_file():
            continue
        with manifest.open("rb") as stream:
            carry=b""
            while chunk:=stream.read(256*1024):
                if marker in carry+chunk:
                    raise HTTPException(409,"SAM используется в сохранённых результатах. Сначала сохраните архивы и согласуйте миграцию.")
                carry=chunk[-len(marker):]

def cache_status():
    try:sig=signature()
    except (OSError,ValueError):sig=None
    with connect() as db:
        row=db.execute("""SELECT count(DISTINCT u.checksum) AS total,
         count(DISTINCT u.checksum) FILTER(WHERE EXISTS (
          SELECT 1 FROM reference_cache c
          WHERE c.source_hash=u.checksum AND c.model_signature=%s)) AS cached
         FROM uploads u WHERE u.kind='reference' AND u.finalized""",
         (sig or "",)).fetchone()
    return {"total":row["total"],"cached":row["cached"],"current_signature":sig}

def rename(source,target):
    source=sam_id(source)
    target=sam_id(target)
    if source==target:return {"sam":source,"renamed":False}
    old_root=owned_directory(REFS/source,REFS)
    new_root=owned_directory(REFS/target,REFS)
    if new_root.exists():raise HTTPException(409,"Папка SAM с новым именем уже существует")
    created=[]
    old_paths=[]
    try:
        with connect() as db:
            _editable(db,source)
            _historical_reference_guard(db,source)
            if db.execute("""SELECT 1 FROM uploads WHERE kind='reference' AND sam=%s LIMIT 1""",
                          (target,)).fetchone():
                raise HTTPException(409,"SAM с таким именем уже существует")
            rows=db.execute("""SELECT id,target_path FROM uploads
                WHERE kind='reference' AND sam=%s AND finalized
                ORDER BY id FOR UPDATE""",(source,)).fetchall()
            if not rows:raise HTTPException(404,"SAM не найдена")
            moves={}
            for row in rows:
                src=owned_file(Path(row["target_path"]),old_root)
                if not src.is_file():raise HTTPException(409,"Исходный Образец недоступен")
                new=owned_file(new_root/src.name,REFS)
                if new.exists():raise HTTPException(409,"Конфликт имён SAM")
                moves[str(src)]=new
                old_paths.append(src)
            new_root.mkdir(parents=True,exist_ok=False)
            for src,new in moves.items():
                try:os.link(src,new,follow_symlinks=False)
                except OSError as exc:
                    if exc.errno!=errno.EXDEV:raise
                    # Safe fallback when mount prevents hardlinks, never overwrite target.
                    with open(src,"rb") as origin,open(new,"xb") as destination:
                        shutil.copyfileobj(origin,destination,1024*1024)
                created.append(new)
            for row in rows:
                src=Path(row["target_path"])
                db.execute("""UPDATE uploads SET sam=%s,target_path=%s WHERE id=%s""",
                    (target,str(moves[str(src)]),row["id"]))
    except Exception:
        # Before DB commit originals remain authoritative. Clean only new files.
        for path in created:path.unlink(missing_ok=True)
        try:new_root.rmdir()
        except OSError:pass
        raise
    # Post-commit cleanup is best effort: crash leaves harmless old hardlinks, not missing originals.
    with connect() as db:
        for old in set(old_paths):
            if not db.execute("SELECT 1 FROM uploads WHERE target_path=%s LIMIT 1",
                              (str(old),)).fetchone():
                old.unlink(missing_ok=True)
    try:old_root.rmdir()
    except OSError:pass
    return {"sam":target,"renamed":True,"photos":len(rows)}

def delete(source):
    source=sam_id(source)
    root=owned_directory(REFS/source,REFS)
    with connect() as db:
        _editable(db,source)
        _historical_reference_guard(db,source)
        rows=db.execute("""SELECT id,target_path FROM uploads
            WHERE kind='reference' AND sam=%s AND finalized FOR UPDATE""",
            (source,)).fetchall()
        if not rows:raise HTTPException(404,"SAM не найдена")
        files=[owned_file(Path(row["target_path"]),root) for row in rows]
        db.execute("""DELETE FROM uploads WHERE kind='reference' AND sam=%s""",(source,))
    # Never unlink a shared target path still referenced by another SAM.
    with connect() as db:
        for path in set(files):
            if not db.execute("SELECT 1 FROM uploads WHERE target_path=%s LIMIT 1",
                              (str(path),)).fetchone():
                path.unlink(missing_ok=True)
    try:root.rmdir()
    except OSError:pass
    return {"deleted":True,"sam":source,"photos":len(rows)}
