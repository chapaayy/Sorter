"""Read-only actual data-mount storage statistics."""
from fastapi import APIRouter,Request
from ...services.storage_usage import usage
from ...services.storage_breakdown import breakdown
from ...services import storage_inventory
from fastapi import Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import HTTPException
from ...storage.reporting import issues
from pathlib import Path
from datetime import datetime, timezone
import json
from app.config import DATA_DIR
from pydantic import BaseModel,StrictBool,StrictInt,Field
from ...storage import admission
from ...security.access_policy import is_owner
from ...services import storage_admin,storage_maintenance
router=APIRouter(prefix="/api/storage",tags=["storage"])

def require_owner(request:Request):
    user=getattr(request.state,"user",None)
    if not user or not is_owner(user):raise HTTPException(403,"Недостаточно прав")

class StorageLimits(BaseModel):
    personal_enabled:StrictBool
    temporary_limit_bytes:StrictInt|None=Field(default=None,ge=0,le=2**63-1)
    disk_reserve_bytes:StrictInt|None=Field(default=None,ge=0,le=2**63-1)

class AccountLimit(BaseModel):
    limit_bytes:StrictInt|None=Field(ge=0,le=2**63-1)

@router.get("/limits")
def limits(request:Request):
    require_owner(request)
    return admission.status()

@router.patch("/limits")
def save_limits(request:Request,payload:StorageLimits):
    require_owner(request)
    return admission.configure(payload.model_dump())

@router.patch("/accounts/{owner_id}/limit")
def save_account_limit(request:Request,owner_id:int,payload:AccountLimit):
    require_owner(request)
    if not 0<owner_id<2**63:raise HTTPException(422,"Неверный аккаунт")
    return admission.set_account(owner_id,payload.limit_bytes)

@router.get("/accounts")
def storage_accounts(request:Request,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
    require_owner(request)
    return storage_admin.accounts(offset,limit)

@router.get("/accounts/{owner_id}")
def storage_account(request:Request,owner_id:int,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
    require_owner(request)
    if not 0<owner_id<2**63:raise HTTPException(422,"Неверный аккаунт")
    return storage_admin.account_detail(owner_id,offset,limit)

@router.get("/operations")
def storage_operations(request:Request):
    require_owner(request)
    return storage_admin.operational()

@router.post("/reconcile",status_code=202)
def reconcile_storage(request:Request):
    require_owner(request)
    return storage_admin.request_reconciliation()

@router.get("/maintenance")
def maintenance_status(request:Request):
    require_owner(request)
    return storage_maintenance.status()

@router.get("/maintenance/{kind}/preview")
def maintenance_preview(request:Request,kind:str):
    require_owner(request)
    return storage_maintenance.preview(kind)

class MaintenanceConfirmation(BaseModel):
    confirmed:StrictBool

@router.post("/maintenance/{kind}",status_code=202)
def maintenance_start(request:Request,kind:str,payload:MaintenanceConfirmation):
    require_owner(request)
    return storage_maintenance.enqueue(kind,payload.confirmed)

@router.get("/host-maintenance/{kind}/preview")
def host_maintenance_preview(request:Request,kind:str):
    require_owner(request)
    return storage_maintenance.host_preview(kind)

@router.post("/host-maintenance/{kind}",status_code=202)
def host_maintenance_start(request:Request,kind:str,payload:MaintenanceConfirmation):
    require_owner(request)
    if kind not in ("storage-cache","storage-logs") or payload.confirmed is not True:
        raise HTTPException(422,"Требуется подтверждение разрешённой операции")
    from .updater import request_host
    return request_host(request,kind)

@router.get("/usage")
def storage_usage():return usage()

@router.get("/accounting/issues")
def accounting_issues(offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200)):
    return issues(limit,offset)

@router.get("/breakdown")
def storage_breakdown():return breakdown()

@router.post("/inventory/scan")
def scan_inventory():
    return storage_inventory.scan()

@router.get("/inventory/files")
def inventory_files(
    snapshot_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    category: str = "",
    search: str = "",
):
    return storage_inventory.files(snapshot_id=snapshot_id, offset=offset, limit=limit,
                                   category=category, search=search)

@router.get("/inventory/report.csv")
def inventory_csv_report(snapshot_id: str):
    filename, content = storage_inventory.csv_report(snapshot_id)
    return StreamingResponse(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


_HOST_REPORT = Path("/host-audit")
_LIVE_REPORT = Path("/logs/audit")

@router.get("/host-audit")
def host_audit_summary():
    """Read only the host-side report; the web container never gets Docker root."""
    path = _HOST_REPORT / "latest.json"
    if not path.is_file():
        return {"available": False, "detail": "Аудит сервера ещё не запускался"}
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(503, "Отчёт аудита сервера недоступен") from exc
    if summary.get("schema") != "map-host-audit-v1":
        raise HTTPException(503, "Неизвестный формат аудита сервера")
    summary["available"] = True
    summary["csv_available"] = (_HOST_REPORT / "latest.csv").is_file()
    summary["write_sites_available"] = (_HOST_REPORT / "latest-write-sites.csv").is_file()
    return summary

@router.get("/host-audit/report.csv")
def host_audit_csv():
    path = _HOST_REPORT / "latest.csv"
    if not path.is_file():
        raise HTTPException(404, "Сначала выполните аудит сервера")
    return FileResponse(
        path=path,
        media_type="text/csv; charset=utf-8",
        filename="map-full-host-file-audit.csv",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/host-audit/write-sites.csv")
def host_audit_write_sites():
    path = _HOST_REPORT / "latest-write-sites.csv"
    if not path.is_file():
        raise HTTPException(404, "Карта записей кода пока не собрана")
    return FileResponse(
        path=path,
        media_type="text/csv; charset=utf-8",
        filename="map-file-write-sites.csv",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/host-audit/report.json")
def host_audit_json():
    """Download the coverage, errors and per-category totals alongside CSV."""
    path = _HOST_REPORT / "latest.json"
    if not path.is_file():
        raise HTTPException(404, "Сначала выполните аудит сервера")
    return FileResponse(
        path=path,
        media_type="application/json",
        filename="map-full-host-audit-summary.json",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/host-audit/live")
def host_live_audit_status():
    path = _LIVE_REPORT / "live-state.json"
    if not path.is_file():
        return {"available": False, "detail": "Наблюдение ещё не запущено"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise HTTPException(503, "Состояние файлового наблюдателя недоступно") from exc
    if payload.get("schema") != "map-live-audit-v1":
        raise HTTPException(503, "Неизвестная версия журнала файлов")
    payload["available"] = True
    # A crashed observer may have written running=true on its last heartbeat.
    try:
        heartbeat = datetime.fromisoformat(payload.get("heartbeat_at", ""))
        age = (datetime.now(timezone.utc) - heartbeat.astimezone(timezone.utc)).total_seconds()
        payload["heartbeat_stale"] = age > 30 or age < -30
    except (ValueError, TypeError):
        payload["heartbeat_stale"] = True
    payload["running"] = bool(payload.get("running")) and not payload["heartbeat_stale"]
    payload["download_available"] = (_LIVE_REPORT / "live-events.jsonl").is_file()
    return payload


@router.get("/host-audit/live-events.jsonl")
def host_live_audit_events():
    """Bounded latest opt-in observer session."""
    path = _LIVE_REPORT / "live-events.jsonl"
    if not path.is_file():
        raise HTTPException(404, "Наблюдение ещё не запущено")
    return FileResponse(
        path=path,
        media_type="application/x-ndjson",
        filename="map-file-live-events.jsonl",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
