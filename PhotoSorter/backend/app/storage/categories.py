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
APP_UID = _contract["app_uid"]
APP_GID = _contract["app_gid"]
CONTAINER_APP_ROOT = Path(_contract["container_app_root"])
HOST_ROOT_DEFAULT = Path(_contract["host_root_default"])
_specs = {item["id"]: MappingProxyType(item) for item in _contract["categories"]}
if len(_specs) != len(_contract["categories"]):
    raise RuntimeError("Duplicate storage category")
Category = Enum("Category", {name.upper(): name for name in _specs}, type=str)
CATEGORIES = MappingProxyType({Category(name): spec for name, spec in _specs.items()})
