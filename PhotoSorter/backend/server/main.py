"""FastAPI assembly: middleware, lifecycle, and independent feature routers."""
from __future__ import annotations
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
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
from .security.access_policy import authorize
from .api.routes import access_requests,auth,batches,downloads,images,logs,models,results,site,storage,thumbnails,references,originals,system,processing_settings

@asynccontextmanager
async def lifespan(app):
    ensure_dirs()
    configure_model_environment()
    wait_and_initialize()
    bootstrap_admin()
    yield

app=FastAPI(title="Outdoor PhotoSorter VPS",version="0.1.0-beta.1",lifespan=lifespan,
            docs_url=None,redoc_url=None,openapi_url=None)
PUBLIC_ENDPOINTS = {("GET", "/api/health"), ("POST", "/api/auth/login"), ("POST", "/api/auth/register")}

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if request.url.path in ("/api/auth/login", "/api/auth/register"):
        return JSONResponse({"detail": "Проверьте поля формы и длину пароля."}, status_code=422)
    return await request_validation_exception_handler(request, exc)

@app.middleware("http")
async def private_api(request:Request,call_next):
    started=time.perf_counter()
    path=request.url.path
    if path.startswith("/api/") and (request.method, path) not in PUBLIC_ENDPOINTS:
        try:
            check_origin(request)
            request.state.user = await asyncio.to_thread(authenticate, request)
            authorize(request.state.user, request.method, path)
        except HTTPException as exc:
            return JSONResponse({"detail":exc.detail},status_code=exc.status_code)
    try:
        return await call_next(request)
    finally:
        system.record(time.perf_counter()-started)

@app.get("/api/health")
def health():return {"status":"ok","version":"0.1.0-beta.1"}

for router in (auth.router,access_requests.router,batches.router,uploads_router,reference_imports_router,work_queue_router,library_notices_router,jobs_router,
               models.router,results.router,images.router,downloads.router,
               logs.router,storage.router,thumbnails.router,references.router,originals.router,system.router,processing_settings.router,site.router):
    app.include_router(router)
