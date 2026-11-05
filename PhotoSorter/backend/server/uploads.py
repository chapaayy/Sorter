"""Resumable file transfer using offsets; originals are never modified after finalize."""
from __future__ import annotations
import asyncio
import hashlib
import os
import re
import threading
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from .database import connect
from .services import operations
from .db.repositories import batches as batch_repository
from .services import thumbnails
from .services.disk_guard import check_admission
from app.config import DATA_DIR
from app.photos.reader import EXTS
from app.photos.labels import check_label

router=APIRouter(prefix='/api',tags=['uploads'])
UPLOADS_DIR=DATA_DIR/'uploads'
REFERENCES_DIR=DATA_DIR/'references'
PART_DIR=DATA_DIR/'incoming'
CHUNK_LIMIT=16*1024*1024
MAX_FILE_BYTES=60*1024*1024
_LOCKS:dict[str,asyncio.Lock]={}
_LOCKS_LOCK=threading.Lock()


def lock_for(upload_id):
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(str(upload_id),asyncio.Lock())


def safe_name(value:str)->str:
    name=Path(value.replace('\\','/')).name.strip()
    if not name or name in ('.','..') or len(name)>200 or not re.fullmatch(r'[\w.()\- +]+',name,re.UNICODE):
        raise HTTPException(422,'Недопустимое имя файла')
    if Path(name).suffix.lower() not in EXTS:raise HTTPException(422,'Поддерживаются только изображения')
    return name


class BeginUpload(BaseModel):
    kind:str
    filename:str
    size:int=Field(gt=0,le=MAX_FILE_BYTES)
    batch_id:str|None=None
    sam:str|None=None
    sha256:str|None=None


def _create_upload(payload:BeginUpload, file_id:uuid.UUID):
    if payload.kind not in ('fo','reference'):raise HTTPException(422,'Недопустимый тип загрузки')
    filename=safe_name(payload.filename)
    batch_id=None;sam=None
    if payload.kind=='fo':
        try:batch_id=uuid.UUID(payload.batch_id or '')
        except ValueError:raise HTTPException(422,'Нужна партия ФО')
    else:
        try:sam=check_label(payload.sam or '')
        except ValueError as exc:raise HTTPException(422,str(exc))
        if not re.match(r'^SAM-\d{4}(?:$|[-])',sam,re.I):
            raise HTTPException(422,'Нужна папка SAM-xxxx')
    if payload.sha256 and not re.fullmatch(r'[0-9a-f]{64}',payload.sha256):
        raise HTTPException(422,'Неверная контрольная сумма')
    check_admission(payload.size)
    token=operations.start(batch_id,'init') if batch_id else None
    recorded=False
    try:
        with connect() as db:
            if payload.kind=='reference' and db.execute(
                 "SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone():
                raise HTTPException(409,'Нельзя изменять Образцы во время сортировки')
            if batch_id:
                batch=db.execute('SELECT delete_state FROM batches WHERE id=%s FOR SHARE',
                                 (batch_id,)).fetchone()
                if not batch:raise HTTPException(404,'Партия не найдена')
                if batch['delete_state']!='active':raise HTTPException(409,'Партия удаляется')
                if db.execute('SELECT 1 FROM jobs WHERE batch_id=%s LIMIT 1',
                              (batch_id,)).fetchone():
                    raise HTTPException(409,'Партия уже использовалась для сортировки')
            db.execute('INSERT INTO uploads(id,kind,batch_id,sam,filename,declared_size,checksum) '
                       'VALUES (%s,%s,%s,%s,%s,%s,%s)',
                       (file_id,payload.kind,batch_id,sam,filename,payload.size,payload.sha256))
            if batch_id:db.execute("UPDATE batches SET upload_state='open' WHERE id=%s",(batch_id,))
        recorded=True
        PART_DIR.mkdir(parents=True,exist_ok=True)
        (PART_DIR/f'{file_id}.part').touch(exist_ok=False)
        return {'id':str(file_id),'offset':0,'size':payload.size}
    except Exception:
        if recorded:
            with connect() as db:
                db.execute('DELETE FROM uploads WHERE id=%s AND NOT finalized',(file_id,))
                if batch_id:batch_repository.refresh_upload_state(db,batch_id)
        raise
    finally:
        if token:operations.finish(token)


@router.post('/uploads')
def create_upload(payload:BeginUpload):
    return _create_upload(payload, uuid.uuid4())


def get_upload(upload_id):
    try: uid=uuid.UUID(upload_id)
    except ValueError:raise HTTPException(404,'Загрузка не найдена')
    with connect() as db:
        row=db.execute('SELECT * FROM uploads WHERE id=%s',(uid,)).fetchone()
    if row is None:raise HTTPException(404,'Загрузка не найдена')
    return row


@router.get('/uploads/{upload_id}')
def upload_status(upload_id:str):
    row=get_upload(upload_id)
    part=PART_DIR/f'{row["id"]}.part'
    offset=part.stat().st_size if part.is_file() else row['received']
    return {'id':str(row['id']),'offset':offset,'size':row['declared_size'],
            'finalized':row['finalized']}


def _append_chunk(path: Path, expected: int, data: bytes, declared_size: int) -> int:
    """Check file offset and write in a worker thread, never on the ASGI event loop."""
    with path.open('r+b') as output:
        actual = output.seek(0, os.SEEK_END)
        if actual != expected:
            raise HTTPException(409, {'expected_offset': actual})
        if actual + len(data) > declared_size:
            raise HTTPException(413, 'Превышен размер файла')
        check_admission(len(data))
        try:
            output.write(data)
            output.flush()
        except OSError:
            output.truncate(actual)
            raise
    return actual + len(data)


def _record_chunk(upload_id: uuid.UUID, received: int) -> None:
    with connect() as db:
        db.execute('UPDATE uploads SET received=%s WHERE id=%s', (received, upload_id))


@router.patch('/uploads/{upload_id}')
async def upload_chunk(upload_id: str, request: Request):
    try:
        offset = int(request.headers.get('upload-offset', '-1'))
    except ValueError:
        raise HTTPException(400, 'Неверный upload-offset')
    if offset < 0:
        raise HTTPException(400, 'Неверный upload-offset')

    # Buffer one bounded 16 MiB request, then offload disk and database work.
    chunks = []
    received = 0
    async for data in request.stream():
        received += len(data)
        if received > CHUNK_LIMIT:
            raise HTTPException(413, 'Превышен размер блока')
        if data:
            chunks.append(data)
    if received == 0:
        raise HTTPException(400, 'Пустой блок')
    payload = b''.join(chunks)

    # Serialize chunks of the same file, not uploads of different files.
    async with lock_for(upload_id):
        row = await asyncio.to_thread(get_upload, upload_id)
        token = await asyncio.to_thread(operations.start, row['batch_id'], 'upload') if row['batch_id'] else None
        try:
            if row['finalized']:
                raise HTTPException(409, 'Файл уже загружен')
            path = PART_DIR / f'{row["id"]}.part'
            if not await asyncio.to_thread(path.is_file):
                raise HTTPException(409, 'Временный файл отсутствует')
            confirmed = await asyncio.to_thread(
                _append_chunk, path, offset, payload, row['declared_size'])
            await asyncio.to_thread(_record_chunk, row['id'], confirmed)
            return {'offset': confirmed}
        finally:
            if token: await asyncio.to_thread(operations.finish, token)


def _finalize_sync(upload_id: str):
    """Hash, verify and register an uploaded photo off the ASGI event loop."""
    row=get_upload(upload_id)
    with connect() as db:
        if row['batch_id']:
            batch=db.execute('SELECT delete_state FROM batches WHERE id=%s FOR SHARE',(row['batch_id'],)).fetchone()
            if not batch or batch['delete_state']!='active':
                raise HTTPException(409,'Партия удаляется или удалена')
        if row['kind']=='reference' and db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone():
            raise HTTPException(409,'Нельзя изменять Образцы во время сортировки')
        if row['kind']=='fo' and db.execute('SELECT 1 FROM jobs WHERE batch_id=%s LIMIT 1',(row['batch_id'],)).fetchone():
            raise HTTPException(409,'Партия уже запущена')
    if row['finalized']:return {'path':row['target_path'],'already_finalized':True}
    path=PART_DIR/f'{row["id"]}.part'
    if not path.exists() or path.stat().st_size!=row['declared_size']:
        raise HTTPException(409,'Файл загружен не полностью')
    with path.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if row['checksum'] and digest!=row['checksum']:raise HTTPException(422,'SHA-256 не совпадает')
    try:
        with Image.open(path) as im:im.verify()
    except (OSError,UnidentifiedImageError,ValueError):
        raise HTTPException(422,'Файл не является корректным изображением')
    # Prevent duplicates when a SAM folder upload is restarted after an error.
    # The transaction lock covers both the duplicate check and registration.
    with connect() as db:
        if row['kind']=='reference':
            db.execute('SELECT pg_advisory_xact_lock(723409134)')
            previous=db.execute(
                "SELECT target_path FROM uploads WHERE kind='reference' AND finalized "
                "AND sam=%s AND checksum=%s LIMIT 1",(row['sam'],digest)).fetchone()
            if previous:
                path.unlink()
                db.execute('DELETE FROM uploads WHERE id=%s',(row['id'],))
                return {'path':previous['target_path'],'sha256':digest,
                        'already_finalized':False,'already_present':True}
        base=UPLOADS_DIR/str(row['batch_id']) if row['kind']=='fo' else REFERENCES_DIR/row['sam']
        base.mkdir(parents=True,exist_ok=True)
        target=base/f'{digest[:20]}_{row["filename"]}'
        if target.exists():
            with target.open('rb') as stream:
                previous_digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if previous_digest!=digest:
                raise HTTPException(409,'Конфликт имён')
            path.unlink()
        else:path.replace(target)
        if row['kind']=='fo': target.chmod(0o444)
        db.execute('UPDATE uploads SET finalized=true,received=declared_size,checksum=%s,target_path=%s '
                   'WHERE id=%s',(digest,str(target),row['id']))
        thumbnails.enqueue(db,row['id'],digest)
        if row['batch_id']:batch_repository.refresh_upload_state(db,row['batch_id'])
    return {'path':str(target),'sha256':digest,'already_finalized':False}


@router.post('/uploads/{upload_id}/finish')
async def finalize(upload_id: str):
    async with lock_for(upload_id):
        row=await asyncio.to_thread(get_upload,upload_id)
        token=await asyncio.to_thread(operations.start,row['batch_id'],'finalize') if row['batch_id'] else None
        try:
            return await asyncio.to_thread(_finalize_sync, upload_id)
        finally:
            if token:await asyncio.to_thread(operations.finish,token)



def _prepare_direct_upload(upload_id: str, payload: BeginUpload) -> dict:
    """Create an idempotent upload id, or check the matching existing upload."""
    uid = uuid.UUID(upload_id)
    try:
        row = get_upload(upload_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        _create_upload(payload, uid)
        row = get_upload(upload_id)

    name = safe_name(payload.filename)
    batch_id = str(row['batch_id']) if row['batch_id'] else ''
    expected_sam = check_label(payload.sam) if payload.kind == 'reference' else ''
    if (row['kind'] != payload.kind or row['filename'] != name or
            row['declared_size'] != payload.size or
            batch_id != (payload.batch_id or '') or
            (row['sam'] or '') != expected_sam):
        raise HTTPException(409, 'Идентификатор занят другой загрузкой')
    return row


@router.put('/uploads/direct/{upload_id}')
async def direct_upload(
    upload_id: str, request: Request, kind: str, filename: str,
    size: int, batch_id: str = '', sam: str = ''
):
    """Single-request upload; keep the resumable PATCH fallback."""
    try:uuid.UUID(upload_id)
    except ValueError:raise HTTPException(404,'Загрузка не найдена')
    payload=BeginUpload(kind=kind,filename=filename,size=size,
                        batch_id=batch_id or None,sam=sam or None)
    async with lock_for(upload_id):
        row=await asyncio.to_thread(_prepare_direct_upload,upload_id,payload)
        token=await asyncio.to_thread(operations.start,row['batch_id'],'upload') if row['batch_id'] else None
        try:
            if row['finalized']:
                return {'already_finalized':True,'path':row['target_path']}
            path=PART_DIR/f"{row['id']}.part"
            length=await asyncio.to_thread(path.stat)
            if length.st_size:
                raise HTTPException(409,'Продолжите загрузку через PATCH')
            offset=0
            buffered=bytearray()
            write_batch_bytes=4*1024*1024
            last_heartbeat=asyncio.get_running_loop().time()
            async for data in request.stream():
                if not data:continue
                if offset+len(buffered)+len(data)>size:
                    raise HTTPException(413,'Превышен размер файла')
                buffered.extend(data)
                if len(buffered)>=write_batch_bytes:
                    offset=await asyncio.to_thread(
                        _append_chunk,path,offset,bytes(buffered),size)
                    buffered.clear()
                if token and asyncio.get_running_loop().time()-last_heartbeat>5:
                    await asyncio.to_thread(operations.heartbeat,token)
                    last_heartbeat=asyncio.get_running_loop().time()
            if buffered:
                offset=await asyncio.to_thread(
                    _append_chunk,path,offset,bytes(buffered),size)
            if offset!=size:
                raise HTTPException(409,'Файл загружен не полностью')
            return await asyncio.to_thread(_finalize_sync,upload_id)
        finally:
            if token:await asyncio.to_thread(operations.finish,token)


@router.get('/references')
def references_status():
    with connect() as db:
        rows=db.execute('SELECT sam, count(*) AS photos FROM uploads '
                        'WHERE kind=\'reference\' AND finalized GROUP BY sam ORDER BY sam').fetchall()
    return {'sam':rows,'total':sum(row['photos'] for row in rows)}


@router.get('/references/files')
def list_reference_files():
    with connect() as db:
        rows=db.execute("SELECT id,sam,filename,checksum,created_at FROM uploads "
                        "WHERE kind='reference' AND finalized ORDER BY sam,created_at").fetchall()
    return {'files':[{'id':str(row['id']),'sam':row['sam'],'name':row['filename'],
                       'sha256':row['checksum']} for row in rows]}


@router.delete('/references/files/{reference_id}')
def remove_reference(reference_id:str):
    try: uid=uuid.UUID(reference_id)
    except ValueError:raise HTTPException(404,'Образец не найден')
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(723409133)')
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone():
            raise HTTPException(409,'Нельзя удалять Образцы во время сортировки')
        row=db.execute("SELECT target_path FROM uploads WHERE id=%s AND kind='reference' AND finalized FOR UPDATE",
                       (uid,)).fetchone()
        if row is None:raise HTTPException(404,'Образец не найден')
        file=Path(row['target_path']).resolve()
        if not file.is_relative_to(REFERENCES_DIR.resolve()):raise HTTPException(409,'Неверный путь Образца')
        db.execute('DELETE FROM uploads WHERE id=%s',(uid,))
    # An identical image may be represented by multiple records: keep it if still referenced.
    with connect() as db:
        referenced=db.execute('SELECT 1 FROM uploads WHERE target_path=%s LIMIT 1',(str(file),)).fetchone()
    if not referenced:file.unlink(missing_ok=True)
    return {'deleted':True}

@router.delete('/uploads/{upload_id}')
async def cancel_upload(upload_id:str):
    """Only remove unfinished transfer; never delete finalized originals."""
    async with lock_for(upload_id):
        row=await asyncio.to_thread(get_upload,upload_id)
        token=await asyncio.to_thread(operations.start,row['batch_id'],'cancel') if row['batch_id'] else None
        try:
            if row['finalized']:raise HTTPException(409,'Готовый оригинал нельзя отменить')
            def remove():
                with connect() as db:
                    target=db.execute("""SELECT id FROM uploads WHERE id=%s AND NOT finalized FOR UPDATE""",
                                      (row['id'],)).fetchone()
                    if not target:raise HTTPException(409,'Загрузка уже завершена')
                    (PART_DIR/f"{row['id']}.part").unlink(missing_ok=True)
                    db.execute("DELETE FROM uploads WHERE id=%s",(row['id'],))
                    if row['batch_id']:batch_repository.refresh_upload_state(db,row['batch_id'])
            await asyncio.to_thread(remove)
            return {"cancelled":True}
        finally:
            if token:await asyncio.to_thread(operations.finish,token)
