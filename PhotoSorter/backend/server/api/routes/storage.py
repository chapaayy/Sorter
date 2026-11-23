"""Read-only actual data-mount storage statistics."""
from fastapi import APIRouter
from ...services.storage_usage import usage
from ...services.storage_breakdown import breakdown
from ...services import storage_inventory
from fastapi import Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import HTTPException
from pathlib import Path
import json
from app.config import DATA_DIR
router=APIRouter(prefix="/api/storage",tags=["storage"])

@router.get("/usage")
def storage_usage():return usage()

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


_HOST_REPORT = DATA_DIR / "audits" / "host"

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
