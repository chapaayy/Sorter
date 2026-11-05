"""Persistent thumbnail tasks: tiny finalize enqueue, independent CPU work and ownership."""
from __future__ import annotations
import io
import os
import tempfile
import uuid
from pathlib import Path
from PIL import Image,ImageOps,UnidentifiedImageError
from ..database import connect
from . import operations
from ..storage import thumbnail_cache as cache
from ..storage.paths import owned_file
from app.config import DATA_DIR

MAX_ATTEMPTS=3
LEASE_SECONDS=300

def enqueue(db,upload_id,checksum):
    """Call inside the upload finalization transaction; never decode in HTTP."""
    db.execute("""INSERT INTO thumbnail_tasks(upload_id,checksum)
        VALUES (%s,%s) ON CONFLICT(upload_id) DO NOTHING""",(upload_id,checksum))

def claim():
    with connect() as db:
        row=db.execute("""SELECT t.upload_id,t.checksum,t.version,u.kind,u.batch_id,u.sam,u.target_path
          FROM thumbnail_tasks t JOIN uploads u ON u.id=t.upload_id
          WHERE u.finalized AND (t.state='queued' OR
            (t.state='running' AND t.lease_until<now()))
            AND t.attempts<%s
          ORDER BY t.created_at,t.upload_id FOR UPDATE OF t SKIP LOCKED LIMIT 1""",
          (MAX_ATTEMPTS,)).fetchone()
        if row:
            db.execute("""UPDATE thumbnail_tasks SET state='running',attempts=attempts+1,
               lease_until=now()+interval '300 seconds',updated_at=now(),
               last_error=NULL WHERE upload_id=%s""",(row["upload_id"],))
        return row

def _image_source(task):
    root=(DATA_DIR/"uploads"/str(task["batch_id"])) if task["kind"]=="fo" else (
        DATA_DIR/"references"/str(task["sam"]))
    path=owned_file(Path(task["target_path"]),root)
    if not path.is_file():raise FileNotFoundError(path)
    return path

def render(source:Path,destination:Path):
    """Bounded EXIF-correct 480px WebP, published atomically in same filesystem."""
    Image.MAX_IMAGE_PIXELS=cache.PIXEL_LIMIT
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".thumb-",suffix=".webp.tmp",dir=destination.parent)
    tmp=Path(name)
    try:
        with Image.open(source) as img:
            img.load()
            img=ImageOps.exif_transpose(img)
            if img.width*img.height>cache.PIXEL_LIMIT:
                raise ValueError("Image too large")
            img.thumbnail((cache.MAX_SIDE,cache.MAX_SIDE),Image.Resampling.LANCZOS)
            if img.mode in ("P","LA","RGBA") or "transparency" in img.info:
                alpha=img.convert("RGBA")
                base=Image.new("RGB",alpha.size,(255,255,255))
                base.paste(alpha,mask=alpha.getchannel("A"))
                img=base
            else:
                img=img.convert("RGB")
            with os.fdopen(fd,"wb") as output:
                img.save(output,format="WEBP",quality=cache.QUALITY,method=4)
                output.flush()
                os.fsync(output.fileno())
            fd=-1
        if destination.is_symlink():raise ValueError("Invalid cached thumbnail")
        os.replace(tmp,destination)
    finally:
        if fd!=-1:os.close(fd)
        tmp.unlink(missing_ok=True)

def complete(task):
    token=None
    try:
        if task["batch_id"]:
            token=operations.start(task["batch_id"],"thumbnail")
        output=cache.location(task["checksum"],task["version"])
        if not output.is_file():
            source=_image_source(task)
            render(source,output)
        with connect() as db:
            # Task may have been deleted with its parent batch/reference.
            db.execute("""UPDATE thumbnail_tasks SET state='ready',lease_until=NULL,
                last_error=NULL,updated_at=now() WHERE upload_id=%s""",(task["upload_id"],))
            _refresh_batch(db,task["batch_id"])
        return "ready"
    except Exception as exc:
        with connect() as db:
            current=db.execute("SELECT attempts FROM thumbnail_tasks WHERE upload_id=%s",
                               (task["upload_id"],)).fetchone()
            if current:
                state="failed" if current["attempts"]>=MAX_ATTEMPTS else "queued"
                db.execute("""UPDATE thumbnail_tasks SET state=%s,lease_until=NULL,
                    last_error=%s,updated_at=now() WHERE upload_id=%s""",
                    (state,f"{type(exc).__name__}: {exc}"[:500],task["upload_id"]))
                _refresh_batch(db,task["batch_id"])
        return "error"
    finally:
        if token:operations.finish(token)

def _refresh_batch(db,batch_id):
    if not batch_id:return
    db.execute("""UPDATE batches SET thumbnail_state=CASE
      WHEN EXISTS (SELECT 1 FROM uploads u LEFT JOIN thumbnail_tasks t ON t.upload_id=u.id
        WHERE u.batch_id=%s AND u.finalized AND
        (t.state IS NULL OR t.state<>'ready')) THEN 'pending'
      ELSE 'ready' END WHERE id=%s""",(batch_id,batch_id))

def counts(batch_id):
    with connect() as db:
        row=db.execute("""SELECT count(*) AS total,
           count(*) FILTER(WHERE t.state='ready') AS ready,
           count(*) FILTER(WHERE t.state='failed') AS failed
           FROM uploads u LEFT JOIN thumbnail_tasks t ON t.upload_id=u.id
           WHERE u.kind='fo' AND u.finalized AND u.batch_id=%s""",(batch_id,)).fetchone()
    return row

def gc_unowned(limit=100,grace_seconds=86400):
    """Only cache files without *any* live upload owner; never raw photographs."""
    import time
    removed=0
    root=cache.ROOT
    if not root.exists():return 0
    for path in root.glob(f"v{cache.VERSION}/*/*.webp"):
        if removed>=limit:break
        try:
            cache.safe_location(path)
            if time.time()-path.stat().st_mtime<grace_seconds:continue
            digest=path.stem
            expected=cache.location(digest)
            if expected!=path:continue
            with connect() as db:
                owner=db.execute("SELECT 1 FROM uploads WHERE finalized AND checksum=%s LIMIT 1",
                                 (digest,)).fetchone()
            if owner:continue
            path.unlink(missing_ok=True)
            removed+=1
        except (OSError,ValueError):continue
    return removed
