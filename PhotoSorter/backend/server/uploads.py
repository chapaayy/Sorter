"""FO-only resumable upload API; references use /api/reference-imports exclusively."""
from __future__ import annotations
import asyncio
import hashlib
import os
import threading
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from PIL import Image, UnidentifiedImageError
from .storage.thumbnail_cache import PIXEL_LIMIT
from .database import connect
from .services import operations
from .services import upload_manifest
from .db.repositories import batches as batch_repository
from .services import thumbnails
from .services.disk_guard import check_admission
from app.config import DATA_DIR
from .services.upload_validation import safe_name,MAX_FILE_BYTES

router=APIRouter(prefix='/api',tags=['uploads'])
UPLOADS_DIR=DATA_DIR/'uploads'
PART_DIR=DATA_DIR/'incoming'
CHUNK_LIMIT=16*1024*1024
_LOCKS:dict[str,asyncio.Lock]={}
_INIT_LOCKS:dict[str,threading.Lock]={}
_LOCKS_LOCK=threading.Lock()


def lock_for(upload_id):
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(str(upload_id),asyncio.Lock())


def init_lock_for(upload_id):
    with _LOCKS_LOCK:
        return _INIT_LOCKS.setdefault(str(upload_id),threading.Lock())


class BeginUpload(BaseModel):
    kind:str
    filename:str
    size:int=Field(gt=0,le=MAX_FILE_BYTES)
    batch_id:str|None=None
    sha256:str|None=None
    client_upload_id:uuid.UUID|None=None


def _create_upload(payload:BeginUpload,file_id:uuid.UUID):
    if payload.kind!='fo':
        raise HTTPException(422,'Образцы загружаются только через /api/reference-imports')
    filename=safe_name(payload.filename)
    try:batch_id=uuid.UUID(payload.batch_id or '')
    except ValueError as exc:raise HTTPException(422,'Нужна партия ФО') from exc
    if payload.sha256 and not re_full_sha(payload.sha256):
        raise HTTPException(422,'Неверная контрольная сумма')
    check_admission(payload.size)
    token=operations.start(batch_id,'init')
    recorded=False
    try:
        with connect() as db:
            # Global order before batch-row locking (same as auto FIFO enqueue).
            db.execute('SELECT pg_advisory_xact_lock(723409133)')
            batch=db.execute('SELECT delete_state FROM batches WHERE id=%s FOR NO KEY UPDATE',
                             (batch_id,)).fetchone()
            if not batch:raise HTTPException(404,'Партия не найдена')
            if batch['delete_state']!='active':raise HTTPException(409,'Партия удаляется')
            if db.execute('SELECT 1 FROM jobs WHERE batch_id=%s LIMIT 1',
                          (batch_id,)).fetchone():
                raise HTTPException(409,'Партия уже использовалась для сортировки')
            upload_manifest.require_expected_upload(db,batch_id,file_id,filename,payload.size)
            db.execute("""INSERT INTO uploads(id,kind,batch_id,filename,
                declared_size,checksum)
                VALUES (%s,'fo',%s,%s,%s,%s)""",
                (file_id,batch_id,filename,payload.size,payload.sha256))
            db.execute("UPDATE batches SET upload_state='open' WHERE id=%s",(batch_id,))
        recorded=True
        PART_DIR.mkdir(parents=True,exist_ok=True)
        (PART_DIR/f'{file_id}.part').touch(exist_ok=False)
        return {'id':str(file_id),'offset':0,'size':payload.size}
    except Exception:
        if recorded:
            with connect() as db:
                db.execute('DELETE FROM uploads WHERE id=%s AND NOT finalized',(file_id,))
                batch_repository.refresh_upload_state(db,batch_id)
        raise
    finally:
        operations.finish(token)


def re_full_sha(digest):
    import re
    return re.fullmatch(r'[0-9a-f]{64}',digest) is not None


@router.post('/uploads')
def create_upload(payload:BeginUpload):
    # The browser persists its UUID before sending. If a VPN cut hides the
    # creation response, re-POSTing the same UUID must not orphan an upload.
    if payload.client_upload_id is None:
        return _create_upload(payload,uuid.uuid4())
    row=_prepare_direct_upload(str(payload.client_upload_id),payload)
    part=PART_DIR/f"{row['id']}.part"
    if not row['finalized'] and not part.exists() and row['received']==0:
        PART_DIR.mkdir(parents=True,exist_ok=True)
        part.touch(exist_ok=True)
    offset=part.stat().st_size if part.is_file() else row['received']
    return {'id':str(row['id']),'offset':offset,'size':row['declared_size'],
            'finalized':row['finalized']}


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
        db.execute('UPDATE uploads SET received=%s,updated_at=now() WHERE id=%s',
                   (received, upload_id))


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


def _finalize_sync(upload_id:str):
    """Verify FO once and reserve its FIFO place on the last manifest file."""
    row=get_upload(upload_id)
    if row['kind']!='fo':
        raise HTTPException(409,'Используйте новую загрузку образцов')
    if row['finalized']:
        return {'path':row['target_path'],'already_finalized':True}
    part=PART_DIR/f'{row["id"]}.part'
    if not part.is_file() or part.stat().st_size!=row['declared_size']:
        current=get_upload(upload_id)
        if current['finalized']:
            return {'path':current['target_path'],'already_finalized':True}
        raise HTTPException(409,'Файл загружен не полностью')
    with part.open('rb') as stream:
        digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if row['checksum'] and digest!=row['checksum']:
        raise HTTPException(422,'SHA-256 не совпадает')
    try:
        with Image.open(part) as im:
            if im.width*im.height>PIXEL_LIMIT:
                raise HTTPException(422,'Слишком большое разрешение изображения')
            im.verify()
    except (OSError,UnidentifiedImageError,ValueError) as exc:
        raise HTTPException(422,'Файл не является корректным изображением') from exc
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(723409133)')
        batch=db.execute("""SELECT delete_state FROM batches
            WHERE id=%s FOR UPDATE""",(row['batch_id'],)).fetchone()
        if not batch or batch['delete_state']!='active':
            raise HTTPException(409,'Партия удаляется или удалена')
        if db.execute('SELECT 1 FROM jobs WHERE batch_id=%s LIMIT 1',
                      (row['batch_id'],)).fetchone():
            raise HTTPException(409,'Партия уже запущена')
        current=db.execute("""SELECT finalized,target_path FROM uploads
            WHERE id=%s FOR UPDATE""",(row['id'],)).fetchone()
        if current['finalized']:
            return {'path':current['target_path'],'already_finalized':True}
        base=UPLOADS_DIR/str(row['batch_id'])
        base.mkdir(parents=True,exist_ok=True)
        target=base/f'{digest[:20]}_{row["filename"]}'
        if target.exists():
            with target.open('rb') as stream:
                old=hashlib.file_digest(stream,'sha256').hexdigest()
            if old!=digest:raise HTTPException(409,'Конфликт имён ФО')
        else:
            # Keep source .part intact until SQL commit, allowing safe retry.
            os.link(part,target)
        target.chmod(0o444)
        db.execute("""UPDATE uploads SET finalized=true,received=declared_size,
            checksum=%s,target_path=%s WHERE id=%s""",(digest,str(target),row['id']))
        thumbnails.enqueue(db,row['id'],digest)
        complete=upload_manifest.reconcile_locked(db,row['batch_id'])
        if complete:
            from .services.auto_processing import enqueue_on_manifest_completion
            enqueue_on_manifest_completion(db,row['batch_id'])
        batch_repository.refresh_upload_state(db,row['batch_id'])
    part.unlink(missing_ok=True)
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
    """Serialize concurrent POST/PUT registration of the same client UUID."""
    with init_lock_for(upload_id):
        return _prepare_direct_upload_locked(upload_id,payload)


def _prepare_direct_upload_locked(upload_id: str, payload: BeginUpload) -> dict:
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
    if (row['kind'] != payload.kind or row['filename'] != name or
            row['declared_size'] != payload.size or
            batch_id != (payload.batch_id or '')):
        raise HTTPException(409, 'Идентификатор занят другой загрузкой')
    return row


@router.put('/uploads/direct/{upload_id}')
async def direct_upload(
    upload_id: str, request: Request, kind: str, filename: str,
    size: int, batch_id: str = ''
):
    """Single-request upload; keep the resumable PATCH fallback."""
    try:uuid.UUID(upload_id)
    except ValueError:raise HTTPException(404,'Загрузка не найдена')
    payload=BeginUpload(kind=kind,filename=filename,size=size,
                        batch_id=batch_id or None)
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
