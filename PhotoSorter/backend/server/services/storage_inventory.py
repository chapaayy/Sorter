"""Bounded read-only snapshot, pagination and CSV from the storage registry."""
from __future__ import annotations
import csv
import io
import threading
from datetime import datetime
from fastapi import HTTPException

_state_lock=threading.Lock()
_scan_lock=threading.Lock()
_snapshot=None

def scan():
    """Capture registry evidence; preserve the previous snapshot on failure."""
    global _snapshot
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(409, "Сканирование уже выполняется")
    try:
        from ..storage.reporting import inventory
        summary, entries = inventory()
        with _state_lock:
            _snapshot = (summary, entries)
        return summary
    finally:
        _scan_lock.release()


def files(*, snapshot_id: str, offset: int = 0, limit: int = 100,
          category: str = "", search: str = ""):
    if not 1 <= limit <= 200 or offset < 0:
        raise HTTPException(422, "Некорректные параметры страницы")
    with _state_lock:
        snapshot = _snapshot
    if snapshot is None:
        raise HTTPException(404, "Сначала запустите сканирование")
    summary, all_entries = snapshot
    if snapshot_id != summary["snapshot_id"]:
        raise HTTPException(409, "Снимок изменился. Запросите новый список")
    search = search.strip().casefold()
    filtered = [
        row for row in all_entries
        if (not category or row["category"] == category)
        and (not search or search in row["path"].casefold()
             or search in (row["owner_name"] or "").casefold())
    ]
    return {
        "snapshot_id": snapshot_id,
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "files": filtered[offset:offset + limit],
    }


_CATEGORY_LABELS = {
    "originals": "Оригиналы ФО",
    "normalized": "Перекодированные ФО",
    "results_files": "Результаты",
    "results_zip": "ZIP результатов",
    "results_temporary": "Временные результаты",
    "reference_objects": "Объекты образцов",
    "reference_gallery": "Галерея образцов",
    "references_zip": "ZIP образцов",
    "reference_uploads": "Загрузка образцов",
    "reference_other": "Прочие образцы",
    "thumbnails": "Миниатюры ФО",
    "reference_thumbnails": "Миниатюры образцов",
    "reference_cache": "Признаки MegaLoc",
    "other_cache": "Кэши",
    "runs": "Данные обработок",
    "logs": "Журналы",
    "incoming": "Незавершённые загрузки",
    "models": "Модели",
    "other": "Прочее",
}
_PURPOSE_LABELS = {
    "permanent": "Постоянный",
    "temporary": "Временный",
    "cache": "Кэш",
    "system": "Системный",
    "service": "Служебный",
    "archive": "Архив",
    "unknown": "Не определён",
}


def _report_cell(value):
    """Prevent user-controlled filenames / FO labels from becoming Excel formulas."""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    result = str(value).replace("\x00", "")
    if result.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + result
    return result


def _validated_snapshot(snapshot_id: str):
    with _state_lock:
        snapshot = _snapshot
    if snapshot is None:
        raise HTTPException(404, "Сначала запустите сканирование")
    if snapshot_id != snapshot[0]["snapshot_id"]:
        raise HTTPException(409, "Снимок изменился. Запросите новый список")
    return snapshot


def csv_report(snapshot_id: str):
    """Stream *all* rows of the captured scan; no pagination or server file."""
    summary, entries = _validated_snapshot(snapshot_id)
    stamp = datetime.fromisoformat(summary["captured_at"]).strftime("%Y%m%d_%H%M%S")
    filename = f"map-file-inventory-{stamp}{'-partial' if summary.get('partial') else ''}.csv"

    def stream():
        # BOM + semicolon separator makes Cyrillic and byte counts readable in Excel.
        yield b"\xef\xbb\xbf"
        out = io.StringIO(newline="")
        writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
        writer.writerow([
            "Путь", "Категория", "Код категории", "Назначение",
            "Владелец / ФО", "Тип связи", "ID связи",
            "Размер файла (байт)", "На диске (байт)",
            "Hardlink без повторного места", "Физических ссылок",
            "Изменён (UTC)",
        ])
        yield out.getvalue().encode("utf-8")
        out.seek(0)
        out.truncate(0)
        for item in entries:
            writer.writerow([_report_cell(value) for value in (
                item["path"],
                _CATEGORY_LABELS.get(item["category"], item["category"]),
                item["category"],
                _PURPOSE_LABELS.get(item["purpose"], item["purpose"]),
                item["owner_name"],
                item["owner_kind"],
                item["owner_id"],
                item["logical_bytes"],
                item["allocated_bytes"],
                "Да" if item["hardlink"] else "Нет",
                item["links"],
                item["modified_at"],
            )])
            yield out.getvalue().encode("utf-8")
            out.seek(0)
            out.truncate(0)

    return filename, stream()
