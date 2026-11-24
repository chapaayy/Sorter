"""Typed app-relative keys, independent of API and database."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import uuid
from string import Formatter
from .categories import Category, CATEGORIES

_RUN = re.compile(r"[0-9]{8}T[0-9]{6}-[a-f0-9]{12}")
_SHA = re.compile(r"[a-f0-9]{64}")
_COMPONENT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}")

def component(value):
    if not isinstance(value, str) or not _COMPONENT.fullmatch(value) or value in (".", "..") or value.endswith("."):
        raise ValueError("Invalid storage component")
    return value

def uuid_key(value):
    value = str(value)
    if str(uuid.UUID(value)) != value:
        raise ValueError("Expected canonical UUID")
    return value

def user_key(value):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]{0,18}", str(value)) or int(value) > 2**63-1:
        raise ValueError("Invalid owner ID")
    return str(value)

def run_key(value):
    if not _RUN.fullmatch(str(value)):
        raise ValueError("Invalid run identifier")
    return str(value)

def digest_key(value):
    if not _SHA.fullmatch(str(value)):
        raise ValueError("Expected full lowercase SHA256")
    return str(value)

def relative_key(value):
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ValueError("Invalid relative key")
    for part in value.split("/"):
        component(part)
    return PurePosixPath(value)

def _field(name, value):
    if name == "user_id":
        return user_key(value)
    if name in {"batch_uuid", "upload_uuid", "session_uuid", "operation_id"}:
        return uuid_key(value)
    if name == "run_id":
        return run_key(value)
    if name in {"hash", "sha256", "model_signature", "cache_key"}:
        return digest_key(value)
    if name == "prefix":
        if not re.fullmatch(r"[a-f0-9]{2}", str(value)):
            raise ValueError("Invalid hash prefix")
        return str(value)
    if name == "version":
        return user_key(value)
    if name == "ext":
        if not re.fullmatch(r"[a-z0-9]{1,10}", str(value)):
            raise ValueError("Invalid extension")
        return str(value)
    if name == "provider":
        if value not in {"huggingface", "torch", "xdg"}:
            raise ValueError("Invalid cache provider")
        return value
    if name == "service":
        if value not in {"api", "worker", "cleanup", "thumbnail", "models"}:
            raise ValueError("Invalid app service")
        return value
    return component(str(value))

@dataclass(frozen=True)
class AppKey:
    category: Category
    relative: PurePosixPath

    def __post_init__(self):
        relative_key(str(self.relative))
        template = CATEGORIES[self.category]["path"]
        if not template.startswith("app/"):
            raise ValueError("Not an app category")
        pieces = list(Formatter().parse(template[4:].rstrip("/")))
        pattern = "".join(re.escape(literal) + (f"(?P<{field}>[^/]+)" if field else "")
                          for literal, field, _, _ in pieces)
        match = re.fullmatch(pattern, str(self.relative))
        if not match:
            raise ValueError("Key does not match category")
        for field, value in match.groupdict().items():
            _field(field, value)
        _check_prefix(match.groupdict())

def _check_prefix(fields):
    if "prefix" in fields:
        digest = fields.get("sha256", fields.get("hash"))
        if digest is not None and fields["prefix"] != digest[:2]:
            raise ValueError("Hash prefix mismatch")

def app_key(category, **fields):
    category = Category(category)
    template = CATEGORIES[category]["path"]
    if not template.startswith("app/"):
        raise ValueError("Not an app category")
    expected = {field for _, field, _, _ in Formatter().parse(template) if field}
    if set(fields) != expected:
        raise ValueError("Wrong storage key fields")
    validated = {field: _field(field, value) for field, value in fields.items()}
    _check_prefix(validated)
    return AppKey(category, relative_key(template[4:].rstrip("/").format(**validated)))
