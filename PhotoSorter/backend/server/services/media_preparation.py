"""Reserve one FIFO task for exactly the files that need normalization."""
from pathlib import Path

from fastapi import HTTPException
from ..database import connect
from ..db.repositories.work_queue import LOCK


def schedule_locked(db, batch_id):
    # The final upload holds the same transaction gate as every FIFO insertion.
    count = db.execute("""SELECT count(*) AS n FROM uploads WHERE batch_id=%s
        AND kind='fo' AND finalized AND media_action='prepare' AND media_output_path IS NULL
        AND media_error IS NULL""", (batch_id,)).fetchone()['n']
    if not count:
        return False
    active = db.execute("""SELECT state FROM work_queue WHERE media_batch_id=%s
        ORDER BY seq DESC LIMIT 1""",(batch_id,)).fetchone()
    if active and active['state'] in ('queued','running','failed','interrupted'):
        return True
    _insert(db,batch_id,count)
    return True


def _insert(db,batch_id,count):
    db.execute("""INSERT INTO work_queue(kind,media_batch_id,media_total_count,media_completed_count,media_failed_count)
        VALUES ('media_preparation',%s,%s,0,0)""",(batch_id,count))


def block_processing(db, batch_id):
    active = db.execute("""SELECT state FROM work_queue WHERE media_batch_id=%s
         ORDER BY seq DESC LIMIT 1""", (batch_id,)).fetchone()
    if active and active['state'] in ('queued','running','failed','interrupted'):
        raise HTTPException(409, 'Сначала дождитесь перекодирования файлов')


def retry(batch_id):
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        batch = db.execute("""SELECT delete_state FROM batches WHERE id=%s FOR UPDATE""",
                           (batch_id,)).fetchone()
        if not batch or batch['delete_state'] != 'active':
            raise HTTPException(404, 'Партия недоступна')
        if db.execute("SELECT 1 FROM batches WHERE id=%s AND upload_manifest_state<>'complete'",(batch_id,)).fetchone():
            raise HTTPException(409, 'Сначала завершите загрузку партии')
        previous = db.execute("""SELECT state FROM work_queue WHERE media_batch_id=%s
             ORDER BY seq DESC LIMIT 1""", (batch_id,)).fetchone()
        if not previous or previous['state'] not in ('failed','completed_with_errors','interrupted'):
            raise HTTPException(409, 'Нет неудачного перекодирования для повтора')
        if db.execute("""SELECT 1 FROM jobs WHERE batch_id=%s AND status IN ('queued','running','stopping')
                         LIMIT 1""", (batch_id,)).fetchone():
            raise HTTPException(409, 'Партия уже сортируется')
        count = db.execute("""UPDATE uploads SET media_error=NULL WHERE batch_id=%s
            AND media_action='prepare' AND media_output_path IS NULL""", (batch_id,)).rowcount
        if not count:
            raise HTTPException(409, 'Нет файлов для повтора')
        _insert(db,batch_id,count)
    return {'batch_id':str(batch_id),'state':'queued'}


def file_errors(batch_id):
    with connect() as db:
        rows = db.execute("""SELECT id,filename,media_error FROM uploads
            WHERE batch_id=%s AND kind='fo' AND finalized AND media_error IS NOT NULL
            ORDER BY created_at,id LIMIT 200""", (batch_id,)).fetchall()
    return {'files':rows}


def playable(row, root):
    from ..storage.paths import owned_file
    source = row['media_output_path'] or (row['target_path'] if row['media_action'] == 'keep' else None)
    if source is None:
        raise FileNotFoundError('Файл ещё не подготовлен')
    return owned_file(Path(source),root)
