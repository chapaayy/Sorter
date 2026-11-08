"""FastAPI assembly: middleware, lifecycle, and independent feature routers."""
from __future__ import annotations
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import JSONResponse
from app.config import ensure_dirs
from app.system.model_store import configure_model_environment
from .auth import authenticate,bootstrap_admin,check_origin
from .database import wait_and_initialize
from .uploads import router as uploads_router
from .api.routes.reference_imports import router as reference_imports_router
from .api.routes.work_queue import router as work_queue_router
from .api.routes.library_notices import router as library_notices_router
from .jobs import router as jobs_router
from .api.routes import auth,batches,downloads,images,logs,models,results,site,storage,thumbnails,references,originals,system,processing_settings,screen_annotations

@asynccontextmanager
async def lifespan(app):
    ensure_dirs()
    configure_model_environment()
    wait_and_initialize()
    bootstrap_admin()
    yield

app=FastAPI(title="Outdoor PhotoSorter VPS",version="0.1.0-beta.1",lifespan=lifespan,
            docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware("http")
async def private_api(request:Request,call_next):
    started=time.perf_counter()
    path=request.url.path
    if path.startswith("/api/") and path not in ("/api/health","/api/auth/login"):
        try:
            check_origin(request)
            await asyncio.to_thread(authenticate,request)
        except HTTPException as exc:
            return JSONResponse({"detail":exc.detail},status_code=exc.status_code)
    try:
        return await call_next(request)
    finally:
        system.record(time.perf_counter()-started)

@app.get("/api/health")
def health():return {"status":"ok","version":"0.1.0-beta.1"}

for router in (auth.router,batches.router,uploads_router,reference_imports_router,work_queue_router,library_notices_router,jobs_router,
               models.router,results.router,images.router,downloads.router,
               logs.router,storage.router,thumbnails.router,references.router,screen_annotations.router,originals.router,system.router,processing_settings.router,site.router):
    app.include_router(router)
