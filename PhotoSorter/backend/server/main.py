"""Authenticated internet-facing PhotoSorter API and static frontend."""
from __future__ import annotations
import asyncio
import os
import re
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel,Field
from app.config import DATA_DIR, PROJECT_DIR, RUNS_DIR, ensure_dirs
from app.results.repository import load_model,load_run
from app.logging.events import read as read_events
from app.photos.reader import EXTS
from app.system.model_store import configure_model_environment, files_present
from app.system.downloads import downloads
from .auth import authenticate,bootstrap_admin,check_origin,login,logout,COOKIE_NAME
from .database import connect,wait_and_initialize
from .uploads import router as uploads_router
from .jobs import router as jobs_router

@asynccontextmanager
async def lifespan(app):
    ensure_dirs()
    configure_model_environment()
    wait_and_initialize()
    bootstrap_admin()
    yield

app=FastAPI(title='Outdoor PhotoSorter VPS',version='4.1.0-vps',lifespan=lifespan,
            docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def private_api(request:Request,call_next):
    path=request.url.path
    if path.startswith('/api/') and path not in ('/api/health','/api/auth/login'):
        try:
            check_origin(request)
            await asyncio.to_thread(authenticate, request)
        except HTTPException as exc:
            return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
    return await call_next(request)

class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=64)
    password:str=Field(min_length=1,max_length=256)

@app.get('/api/health')
def health():return {'status':'ok','version':'4.1.0-vps'}

@app.post('/api/auth/login')
def sign_in(credentials:Credentials,request:Request):
    check_origin(request)
    token=login(credentials.username,credentials.password)
    response=JSONResponse({'username':credentials.username})
    response.set_cookie(COOKIE_NAME,token,max_age=7*24*3600,secure=True,httponly=True,samesite='strict',path='/')
    return response

@app.post('/api/auth/logout')
def sign_out(request:Request):
    logout(request)
    response=JSONResponse({'ok':True})
    response.delete_cookie(COOKIE_NAME,path='/')
    return response

@app.get('/api/auth/me')
def me(request:Request):return authenticate(request)

app.include_router(uploads_router)
app.include_router(jobs_router)

@app.get('/api/models')
def model_info():
    present=files_present()
    return {'models':[{'id':'megaloc','title':'MegaLoc','available':present,
                       'reason':'' if present else 'Модель ещё не загружена',
                       'downloadable':True}], 'device':'cpu','downloads':downloads.status()}

@app.post('/api/models/megaloc/download',status_code=202)
def download_model():
    with connect() as db:
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone():
            raise HTTPException(409,'Дождитесь окончания сортировки')
    try:return downloads.start('megaloc')
    except RuntimeError as exc:raise HTTPException(409,str(exc))

@app.get('/api/results/{run_id}')
def results_overview(run_id:str):
    try:return load_run(run_id)
    except (FileNotFoundError,ValueError):raise HTTPException(404,'Запуск не найден')

@app.get('/api/results/{run_id}/megaloc')
def results(run_id:str):
    try:
        rows=load_model(run_id,'megaloc')
        counts={}
        for item in rows:
            label=item['assigned_sam'];counts[label]=counts.get(label,0)+1
        return {'model':'megaloc','rows':rows,'sam_counts':counts}
    except (FileNotFoundError,ValueError):raise HTTPException(404,'Результаты не найдены')

@app.get('/api/logs/{run_id}')
def logs(run_id:str,model:str|None=None,level:str|None=None):
    try:
        load_run(run_id)
        return {'events':read_events(run_id,model=model,level=level)}
    except (FileNotFoundError,ValueError):raise HTTPException(404,'Запуск не найден')


def safe_manifest(run_id):
    try: return load_model(run_id,'megaloc')
    except (FileNotFoundError,ValueError):raise HTTPException(404,'Результат не найден')


def file_allowed(file:Path):
    roots=[(DATA_DIR/name).resolve() for name in ('references','uploads','outputs')]
    resolved=file.resolve()
    if not any(resolved.is_relative_to(root) for root in roots):raise HTTPException(404,'Файл недоступен')
    if not file.is_file() or file.suffix.lower() not in EXTS:raise HTTPException(404,'Файл не найден')
    return file


@app.get('/api/images/{run_id}/megaloc/{index}')
def image(run_id:str,index:int,kind:str='query',candidate:int=0):
    rows=safe_manifest(run_id)
    if index<0 or index>=len(rows):raise HTTPException(404,'Фотография не найдена')
    row=rows[index]
    if kind=='query':filename=row['query']
    elif kind=='copy':filename=row['copy']
    elif kind=='reference':
        top=row.get('top',[])
        if not 0<=candidate<len(top):raise HTTPException(404,'Образец не найден')
        filename=top[candidate]['reference']
    else:raise HTTPException(422,'Неверный тип изображения')
    return FileResponse(file_allowed(Path(filename)))


@app.get('/api/download/{run_id}')
def download_results(run_id:str,sam:str|None=None):
    import zipstream
    rows=safe_manifest(run_id)
    selected=[]
    for row in rows:
        if sam and row['assigned_sam']!=sam:continue
        file=file_allowed(Path(row['copy']))
        selected.append((file,f'{row["assigned_sam"]}/{file.name}'))
    if not selected:raise HTTPException(404,'Нет фотографий для архива')
    stream=zipstream.ZipStream(compress_type=zipfile.ZIP_STORED)
    for file,name in selected:stream.add_path(file,arcname=name)
    headers={'Content-Disposition':f'attachment; filename="photosorter-{run_id}.zip"',
             'Cache-Control':'no-store'}
    return StreamingResponse(stream,media_type='application/zip',headers=headers)

FRONTEND=PROJECT_DIR/'frontend'/'static'
@app.get('/',include_in_schema=False)
def index():return FileResponse(FRONTEND/'index.html')

@app.get('/static/{filename}',include_in_schema=False)
def asset(filename:str):
    if filename not in ('app.js','style.css'):raise HTTPException(404)
    return FileResponse(FRONTEND/filename)
