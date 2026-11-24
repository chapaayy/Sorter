"""Persistent thumbnail tasks: tiny finalize enqueue, independent CPU work and ownership."""
from __future__ import annotations
import io
import os
import uuid
from pathlib import Path
from PIL import Image,ImageOps,ImageCms,UnidentifiedImageError
from ..database import connect
from . import operations
from ..storage import thumbnail_cache as cache
from ..storage.paths import owned_file,batch_dir
from app.config import DATA_DIR
from app import config
from app.storage.filesystem import atomic_write,safe_unlink
from app.storage.temporary import temporary_operation
from ..storage.reference_lifecycle import ReadPin,try_collect
from ..storage.reference_objects import object_root

MAX_ATTEMPTS=3
LEASE_SECONDS=300

def enqueue(db,upload_id,checksum):
    """Call inside the upload finalization transaction; never decode in HTTP."""
    db.execute("""INSERT INTO thumbnail_tasks(upload_id,checksum)
        VALUES (%s,%s) ON CONFLICT(upload_id) DO NOTHING""",(upload_id,checksum))
    db.execute("""DELETE FROM thumbnail_gc_candidates c USING uploads u LEFT JOIN batches b ON b.id=u.batch_id
        WHERE u.id=%s AND c.checksum=%s AND c.version=%s
          AND c.scope_key=COALESCE(b.owner_id::text,'shared')""",(upload_id,checksum,cache.VERSION))

def claim():
    with connect() as db:
        # Last crashed attempt must become a visible failed task, never stuck running.
        db.execute("""UPDATE thumbnail_tasks SET state='failed',
            last_error='Thumbnail worker stopped after maximum retries',
            lease_until=NULL,updated_at=now()
            WHERE state='running' AND lease_until<now() AND attempts>=%s""",
            (MAX_ATTEMPTS,))
        row=db.execute("""SELECT t.upload_id,t.checksum,t.version,u.kind,u.batch_id,u.sam,u.target_path,
                 u.media_action,u.original_media_type,b.owner_id
          FROM thumbnail_tasks t JOIN uploads u ON u.id=t.upload_id
          LEFT JOIN batches b ON b.id=u.batch_id
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
    root=batch_dir(task["batch_id"]) if task["kind"]=="fo" else (
        object_root())
    path=owned_file(Path(task["target_path"]),root)
    if not path.is_file():raise FileNotFoundError(path)
    return path

def render(source:Path,destination:Path):
    """Bounded EXIF-correct 480px WebP, published atomically in same filesystem."""
    from ..media.formats import register_heif
    register_heif()
    Image.MAX_IMAGE_PIXELS=cache.PIXEL_LIMIT
    with Image.open(source) as img:
        img.load()
        img=ImageOps.exif_transpose(img)
        # Convert tagged RGB sources to sRGB; malformed ICC never alters originals.
        icc=img.info.get("icc_profile")
        if icc and len(icc)<=131072 and img.mode=="RGB":
            try:
                src_profile=ImageCms.ImageCmsProfile(io.BytesIO(icc))
                img=ImageCms.profileToProfile(img,src_profile,
                    ImageCms.createProfile("sRGB"),outputMode="RGB")
            except (OSError,ValueError,TypeError):
                pass
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
        with atomic_write(config.APP_STORAGE_ROOT,destination.relative_to(config.APP_STORAGE_ROOT)) as output:
            img.save(output,format="WEBP",quality=cache.QUALITY,method=4)

def complete(task):
    token=None
    pin=None
    try:
        if task["batch_id"]:
            token=operations.start(task["batch_id"],"thumbnail")
        pin=ReadPin()
        if task["kind"]=="fo" and task["owner_id"] is None:raise ValueError("Missing thumbnail owner")
        output=cache.safe_location(cache.location(task["checksum"],task["version"],owner_id=task["owner_id"]))
        if not output.is_file():
            source=_image_source(task)
            if (task.get("original_media_type") or "").startswith("video/"):
                from ..media.video import poster
                with temporary_operation(config.APP_STORAGE_ROOT,"thumbnail") as tmp:
                    frame=Path(tmp)/'poster.jpg'
                    poster(source,frame)
                    render(frame,output)
            else:
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
        if pin:pin.close()
        if token:operations.finish(token)

def _refresh_batch(db,batch_id):
    if not batch_id:return
    db.execute("""UPDATE batches SET thumbnail_state=CASE
      WHEN EXISTS (SELECT 1 FROM uploads u LEFT JOIN thumbnail_tasks t ON t.upload_id=u.id
        WHERE u.batch_id=%s AND u.finalized AND (u.original_media_type IS NULL OR u.media_action IS NOT NULL) AND
        (t.state IS NULL OR t.state<>'ready')) THEN 'pending'
      ELSE 'ready' END WHERE id=%s""",(batch_id,batch_id))

def counts(batch_id):
    with connect() as db:
        row=db.execute("""SELECT count(*) AS total,
           count(*) FILTER(WHERE t.state='ready') AS ready,
           count(*) FILTER(WHERE t.state='failed') AS failed
           FROM uploads u LEFT JOIN thumbnail_tasks t ON t.upload_id=u.id
           WHERE u.kind='fo' AND u.finalized AND (u.original_media_type IS NULL OR u.media_action IS NOT NULL) AND u.batch_id=%s""",(batch_id,)).fetchone()
    return row

def _has_owner(db,digest,owner):
    if owner is None:
        from .reference_gc import _inconsistent_pins
        if _inconsistent_pins(db):return True
        # Historical/pinned library members also protect their shared previews.
        return db.execute("""SELECT 1 FROM uploads WHERE kind='reference' AND finalized AND checksum=%s
            UNION ALL SELECT 1 FROM reference_version_members WHERE source_hash=%s
            UNION ALL SELECT 1 FROM reference_import_files f JOIN reference_import_sessions s ON s.id=f.session_id
            WHERE f.checksum=%s AND s.upload_state<>'cancelled' AND s.preparation_state NOT IN ('completed','stopped')
            LIMIT 1""",(digest,digest,digest)).fetchone()
    return db.execute("""SELECT 1 FROM uploads u JOIN batches b ON b.id=u.batch_id
        WHERE u.kind='fo' AND u.finalized AND u.checksum=%s AND b.owner_id=%s LIMIT 1""",(digest,owner)).fetchone()

def gc_unowned(limit=100,grace_seconds=86400):
    """Remove canonical ownerless previews only, synchronized with all readers."""
    import time
    removed=0
    for owner,root in cache.roots():
        for path in root.glob("*/*.webp"):
            if removed>=limit:return removed
            try:
                expected=cache.location(path.stem,owner_id=owner)
                if expected!=path:continue
                cache.safe_location(path)
                if time.time()-path.stat().st_mtime<grace_seconds:continue
                with connect() as db:
                    if not try_collect(db):return removed
                    scope="shared" if owner is None else str(owner)
                    params=(scope,path.stem,cache.VERSION)
                    if _has_owner(db,path.stem,owner):
                        db.execute("DELETE FROM thumbnail_gc_candidates WHERE scope_key=%s AND checksum=%s AND version=%s",params)
                        continue
                    db.execute("""INSERT INTO thumbnail_gc_candidates(scope_key,checksum,version)
                        VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",params)
                    due=db.execute("""SELECT 1 FROM thumbnail_gc_candidates WHERE scope_key=%s AND checksum=%s AND version=%s
                        AND unowned_since<=now()-(%s*interval '1 second')""",(*params,grace_seconds)).fetchone()
                    if not due:continue
                    safe_unlink(config.APP_STORAGE_ROOT,path.relative_to(config.APP_STORAGE_ROOT),missing_ok=True)
                    db.execute("DELETE FROM thumbnail_gc_candidates WHERE scope_key=%s AND checksum=%s AND version=%s",params)
                    removed+=1
            except (OSError,ValueError):continue
    return removed

