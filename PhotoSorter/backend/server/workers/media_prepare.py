"""Convert immutable originals using the same exclusive leader as MegaLoc."""
import os
import shutil
import time
from pathlib import Path

from app.config import DATA_DIR
from ..database import connect
from ..media.formats import normalized_image
from ..media.video import encode
from ..storage.paths import owned_file
from ..services import operations,disk_guard


def run(item, *, stopping):
    batch_id, seq = item['id'], item['seq']
    token = None
    checked = 0.0
    cancelled = False

    def stop():
        nonlocal checked,cancelled
        if stopping():return True
        now = time.monotonic()
        if now - checked > 2:
            checked = now
            if token: operations.heartbeat(token)
            with connect() as db:
                row = db.execute("SELECT delete_state FROM batches WHERE id=%s",(batch_id,)).fetchone()
                cancelled = not row or row['delete_state'] != 'active'
        return cancelled

    status, error = 'interrupted', None
    try:
        token = operations.start(batch_id, 'media_prepare')
        with connect() as db:
            settings = db.execute("""SELECT media_image_format,media_video_format
                FROM batches WHERE id=%s""",(batch_id,)).fetchone()
            rows = db.execute("""SELECT id,filename,target_path,original_media_type
                FROM uploads WHERE batch_id=%s AND kind='fo' AND finalized
                AND media_action='prepare' AND media_output_path IS NULL AND media_error IS NULL
                ORDER BY created_at,id""",(batch_id,)).fetchall()
        root = DATA_DIR / 'uploads' / str(batch_id)
        dest = root / '.normalized'
        if dest.is_symlink():raise ValueError('Недопустимый каталог подготовки')
        dest.mkdir(exist_ok=True)
        failures = 0
        for row in rows:
            if stop():raise InterruptedError()
            is_video = (row['original_media_type'] or '').startswith('video/')
            ext = settings['media_video_format' if is_video else 'media_image_format']
            output = dest / f"{row['id']}.{ext}"
            partial = dest / f".{row['id']}.part.{ext}"
            partial.unlink(missing_ok=True)
            failure = None
            duration = None
            try:
                source = owned_file(Path(row['target_path']), root)
                usage=shutil.disk_usage(dest)
                if usage.free-max(64*1024**2,source.stat().st_size)<disk_guard.reserve(usage.total):
                    raise ValueError('Недостаточно места для подготовленной копии')
                if is_video:duration=encode(source,partial,ext,stop=stop).duration
                else:normalized_image(source,partial,ext)
                if stop():raise InterruptedError()
                with partial.open('rb') as file:os.fsync(file.fileno())
                partial.chmod(0o444)
                os.replace(partial, output)
            except InterruptedError:
                raise
            except Exception as exc:
                # Do not expose command lines, local paths or raw FFmpeg output.
                failure = str(exc)[:300] if isinstance(exc,ValueError) else 'Не удалось прочитать или перекодировать файл'
                failures += 1
            finally:
                partial.unlink(missing_ok=True)
            with connect() as db:
                db.execute("UPDATE uploads SET media_output_path=%s,media_error=%s,media_duration=coalesce(%s,media_duration) WHERE id=%s",
                           (str(output) if not failure else None,failure,duration,row['id']))
                db.execute("""UPDATE work_queue SET media_completed_count=media_completed_count+1,
                    media_failed_count=media_failed_count+%s WHERE seq=%s""",(int(bool(failure)),seq))
        status = 'completed_with_errors' if failures else 'completed'
        if failures:error = f'Не удалось перекодировать файлов: {failures}'
    except InterruptedError:
        status = 'stopped' if cancelled else 'interrupted'
        error = 'Перекодирование прервано'
    except Exception:
        status, error = 'failed', 'Не удалось запустить перекодирование'
        raise
    finally:
        with connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(723409133)")
            batch = db.execute("SELECT delete_state FROM batches WHERE id=%s FOR UPDATE",(batch_id,)).fetchone()
            if batch and batch['delete_state'] != 'active':status = 'stopped'
            db.execute("""UPDATE work_queue SET state=%s,media_error=%s,finished_at=now()
                WHERE seq=%s AND state='running'""",(status,error,seq))
            if status in ('completed','completed_with_errors') and batch and batch['delete_state']=='active':
                from ..services.auto_processing import enqueue_on_manifest_completion
                enqueue_on_manifest_completion(db,batch_id)
        if token:operations.finish(token)
