"""Load the single versioned storage policy; no duplicate category table."""
import json
from pathlib import Path
from types import MappingProxyType
from enum import Enum

CONTRACT_PATH = Path(__file__).resolve().parents[4] / "docs/storage-layout-v2.json"
with CONTRACT_PATH.open(encoding="utf-8") as stream:
    _contract = json.load(stream)
if _contract["layout_version"] != 2:
    raise RuntimeError("Unsupported storage contract")
LAYOUT_VERSION = _contract["layout_version"]
ARCHIVE_TTL_SECONDS = _contract["archive_ttl_seconds"]
ARCHIVE_SWEEP_SECONDS = _contract["archive_sweep_seconds"]
TEMPORARY_GRACE_SECONDS = _contract["temporary_grace_seconds"]
LOG_BUDGETS_MIB = MappingProxyType(_contract["log_budgets_mib"])
RUN_LOG_BUDGET_MIB = _contract["run_log_budget_mib"]
APP_UID = _contract["app_uid"]
APP_GID = _contract["app_gid"]
CONTAINER_APP_ROOT = Path(_contract["container_app_root"])
HOST_ROOT_DEFAULT = Path(_contract["host_root_default"])
_specs = {item["id"]: MappingProxyType(item) for item in _contract["categories"]}
if len(_specs) != len(_contract["categories"]):
    raise RuntimeError("Duplicate storage category")
Category = Enum("Category", {name.upper(): name for name in _specs}, type=str)
CATEGORIES = MappingProxyType({Category(name): spec for name, spec in _specs.items()})

# Directory bootstrap is generated from the same policy templates. Dynamic
# owner, run and upload identifiers are never materialized by the installer.
FOUNDATION_PATHS = MappingProxyType(_contract["foundation_paths"])
def _static_directory(template):
    if template.startswith("@"):
        return None
    parts = []
    for part in template.rstrip("/").split("/"):
        if "{" in part:
            break
        parts.append(part)
    if len(parts) == len(template.rstrip("/").split("/")) and not template.endswith("/"):
        parts.pop()
    return "/".join(parts) if parts else None

BOOTSTRAP_DIRS = tuple(sorted({
    folder for spec in CATEGORIES.values()
    if (folder := _static_directory(spec["path"]))
} | set(_contract["bootstrap_extra_directories"])))
APP_BOOTSTRAP_DIRS = tuple(folder[4:] for folder in BOOTSTRAP_DIRS if folder.startswith("app/"))
