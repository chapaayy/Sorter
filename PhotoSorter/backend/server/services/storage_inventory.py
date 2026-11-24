"""Read-only, on-demand inventory of MAP-owned data and model files.

An inventory is a point-in-time snapshot, NOT a retention/cleanup engine. No
paths are opened for content reading and nothing is written to disk. Do not
mistake this for a database of every historic transient file: files that have
already disappeared before the scan are not observable.
"""
from __future__ import annotations

import csv
import io
import os
import stat as statlib
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from app.config import DATA_DIR, MODELS_DIR
from .storage_breakdown import _kind, _metadata, ROOT_ORDER

MAX_FILES = 250_000
MAX_SECONDS = 15.0
_UNSCANNED = (
    "PostgreSQL files and WAL (separate Docker volume)",
    "Caddy files (separate Docker volumes)",
    "Docker images, layers, build cache and container logs",
    "System and unmounted container temporary directories",
)

_state_lock = threading.Lock()
_scan_lock = threading.Lock()
_snapshot = None


def _purpose(category: str, parts: tuple[str, ...]) -> str:
    name = parts[-1].lower()
    if (name.endswith((".part", ".tmp", ".lock"))
            or ".building" in parts
            or name.startswith((".thumb-", ".archive-", ".references-"))
            or any(p.startswith("media-frames-") for p in parts)):
        return "temporary"
    if category in ("incoming", "reference_uploads", "results_temporary"):
        return "temporary"
    if category in ("reference_cache", "other_cache"):
        return "cache"
    if category in ("models",):
        return "system"
    if category in ("runs", "logs", "reference_other"):
        return "service"
    if category in ("results_zip", "references_zip"):
        return "temporary"
    if category == "other":
        return "unknown"
    return "permanent"


def _owner(parts: tuple[str, ...], names: dict, jobs: dict):
    if len(parts) < 2:
        return ("system", None, None)
    section, identity = parts[0], parts[1]
    if section == "uploads":
        return ("batch", identity, names.get(identity))
    if section in ("runs", "outputs"):
        batch_id = jobs.get(identity)
        return ("batch", batch_id, names.get(batch_id)) if batch_id else ("run", identity, None)
    if section == "reference_staging":
        return ("reference_session", identity, None)
    if section == "references":
        return ("construction", identity, None)
    return ("system", None, None)


def _collect(data_dir: Path, models_dir: Path, names: dict, jobs: dict,
             *, max_files: int = MAX_FILES, max_seconds: float = MAX_SECONDS):
    """Perform a bounded, symlink-safe scan. Inject paths in unit tests."""
    began = time.monotonic()
    stop_at = began + max_seconds
    entries = []
    seen_inodes = set()
    categories = {}
    skipped = 0
    partial = False
    checked_roots = []

    for root_name, root in (("data", data_dir), ("models", models_dir)):
        if time.monotonic() >= stop_at or len(entries) >= max_files:
            partial = True
            break
        if root.is_symlink():
            skipped += 1
            partial = True
            continue
        if not root.is_dir():
            skipped += 1
            partial = True
            continue
        checked_roots.append(root_name)

        def on_error(_error):
            nonlocal skipped, partial
            skipped += 1
            partial = True

        for folder, dirs, filenames in os.walk(root, followlinks=False, onerror=on_error):
            if time.monotonic() >= stop_at or len(entries) >= max_files:
                partial = True
                break
            safe_dirs = []
            for d in dirs:
                if (Path(folder) / d).is_symlink():
                    skipped += 1
                    partial = True
                else:
                    safe_dirs.append(d)
            if Path(folder) == root and root_name == "data":
                priority = {name: index for index, name in enumerate(ROOT_ORDER)}
                dirs[:] = sorted(safe_dirs, key=lambda name: (priority.get(name, 100), name))
            else:
                dirs[:] = sorted(safe_dirs)
            for filename in sorted(filenames):
                if time.monotonic() >= stop_at or len(entries) >= max_files:
                    partial = True
                    break
                path = Path(folder) / filename
                try:
                    if path.is_symlink():
                        skipped += 1
                        partial = True
                        continue
                    item = path.stat(follow_symlinks=False)
                    if not statlib.S_ISREG(item.st_mode):
                        continue
                except OSError:
                    skipped += 1
                    partial = True
                    continue
                relative = path.relative_to(root).parts
                category = "models" if root_name == "models" else _kind(relative)
                purpose = _purpose(category, relative)
                owner_kind, owner_id, owner_name = (
                    ("system", None, None) if root_name == "models" else _owner(relative, names, jobs)
                )
                inode = (item.st_dev, item.st_ino)
                duplicate = inode in seen_inodes
                seen_inodes.add(inode)
                physical = 0 if duplicate else max(0, item.st_blocks * 512)
                stats = categories.setdefault(category, {
                    "files": 0, "logical_bytes": 0, "allocated_bytes": 0,
                    "hardlink_paths": 0,
                })
                stats["files"] += 1
                stats["logical_bytes"] += item.st_size
                stats["allocated_bytes"] += physical
                stats["hardlink_paths"] += int(duplicate)
                entries.append({
                    "path": ("PhotoSorter/data/" if root_name == "data" else "Models/") +
                            "/".join(relative),
                    "category": category,
                    "purpose": purpose,
                    "owner_kind": owner_kind,
                    "owner_id": owner_id,
                    "owner_name": owner_name,
                    "logical_bytes": item.st_size,
                    "allocated_bytes": physical,
                    "hardlink": duplicate,
                    "links": item.st_nlink,
                    "modified_at": datetime.fromtimestamp(
                        item.st_mtime, timezone.utc
                    ).isoformat(),
                })
            if partial and (time.monotonic() >= stop_at or len(entries) >= max_files):
                break

    entries.sort(key=lambda value: (-value["allocated_bytes"], value["path"]))
    captured_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "snapshot_id": str(uuid.uuid4()),
        "captured_at": captured_at,
        "files_scanned": len(entries),
        "allocated_bytes": sum(s["allocated_bytes"] for s in categories.values()),
        "logical_bytes": sum(s["logical_bytes"] for s in categories.values()),
        "categories": categories,
        "skipped_paths": skipped,
        "partial": partial,
        "scan_seconds": round(time.monotonic() - began, 2),
        "checked_roots": checked_roots,
        "not_scanned": list(_UNSCANNED),
        "description": "Snapshot of visible app data/model mounts; not a live file registry",
    }
    return summary, entries


def scan():
    """Explicit manual scan. Previous snapshot survives a failed scan."""
    global _snapshot
    if not _scan_lock.acquire(blocking=False):
        raise HTTPException(409, "Сканирование уже выполняется")
    try:
        try:
            names, jobs = _metadata()
            metadata_available = True
        except Exception:
            names, jobs = {}, {}
            metadata_available = False
        summary, entries = _collect(DATA_DIR, MODELS_DIR, names, jobs)
        summary["batch_metadata_available"] = metadata_available
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
    "thumbnails": "Миниатюры",
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
