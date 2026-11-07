"""One-time verified baseline from finalized legacy reference rows.

Stage 1 never changes how legacy recognition reads images. The baseline is
metadata only. The future stage 3 activation MUST reconcile legacy edits and
materialize immutable storage before relying on any pinned version.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from app.config import DATA_DIR
from ..db.repositories import reference_versions

LOG = logging.getLogger(__name__)
SHA256 = re.compile(r"[0-9a-f]{64}\Z")

def _verified_member(row, root: Path):
    raw = row["target_path"]
    if not raw:
        raise ValueError("reference missing target_path")
    path = Path(raw)
    if not path.is_absolute() or not path.is_relative_to(root):
        raise ValueError("reference path outside published directory")
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError("symlink reference path is not trusted")
        cursor = cursor.parent
    if not path.is_file():
        raise ValueError("finalized reference file is missing")
    if not path.resolve().is_relative_to(root):
        raise ValueError("reference path resolves outside published directory")
    size = path.stat().st_size
    if size != row["declared_size"]:
        raise ValueError("reference size differs from finalized upload")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream,"sha256").hexdigest()
    recorded = row["checksum"]
    if recorded is not None and (not SHA256.fullmatch(recorded) or recorded != digest):
        raise ValueError("reference SHA-256 differs from finalized upload")
    return {
        "reference_id":row["id"], "sam":row["sam"],
        "filename":row["filename"], "source_hash":digest,
        "target_path":str(path), "declared_size":size
    }

def ensure_baseline(db, *, reference_root=None, model_signature=None):
    """Publish V1 once, or leave an explicit error without blocking the old site.

    Must execute within a database transaction. Lock order matches the upload
    finalizer: scheduling advisory key 133 before the migration key 134.
    If any finalized file is invalid, publish *nothing*, not a partial V1.
    """
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    state = db.execute("""
        SELECT current_version_id FROM reference_library_state WHERE id=1 FOR UPDATE
    """).fetchone()
    if state is None:
        raise RuntimeError("reference version migration has not been applied")
    if state["current_version_id"] is not None:
        return reference_versions.current(db)
    root = (Path(reference_root) if reference_root is not None
            else DATA_DIR / "references").resolve()
    rows = db.execute("""
        SELECT id,sam,filename,checksum,target_path,declared_size
        FROM uploads WHERE kind='reference' AND finalized ORDER BY sam,id
        FOR SHARE
    """).fetchall()
    try:
        verified = [_verified_member(row,root) for row in rows]
    except (OSError,ValueError) as exc:
        # No user-visible API depends on this metadata in stage 1. Fail closed
        # only for the new snapshot, while leaving the existing API operational.
        LOG.warning("Reference baseline needs manual attention: %s",exc)
        db.execute("""
            UPDATE reference_library_state
            SET baseline_state='needs_attention',baseline_error=%s,updated_at=now()
            WHERE id=1
        """,(str(exc),))
        return reference_versions.current(db)

    canonical = [{
        "id":str(item["reference_id"]), "sam":item["sam"],
        "filename":item["filename"], "hash":item["source_hash"],
        "path":item["target_path"], "size":item["declared_size"]
    } for item in verified]
    digest = hashlib.sha256(json.dumps(canonical,ensure_ascii=False,
        sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
    if model_signature is None:
        from app.system.model_store import signature
        model_signature = signature()
    version = db.execute("""
        INSERT INTO reference_library_versions
            (version_number,manifest_digest,model_signature)
        VALUES (1,%s,%s) RETURNING id
    """,(digest,model_signature)).fetchone()["id"]
    if verified:
        with db.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO reference_version_members
                    (version_id,reference_id,sam,filename,source_hash,target_path,declared_size)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,[(version,item["reference_id"],item["sam"],item["filename"],
                 item["source_hash"],item["target_path"],item["declared_size"])
                for item in verified])
    db.execute("""
        UPDATE reference_library_state
        SET current_version_id=%s,baseline_state='ready',
            baseline_error=NULL,updated_at=now() WHERE id=1
    """,(version,))
    db.execute("""
        INSERT INTO reference_library_events(version_id,event_kind,actor,details)
        VALUES (%s,'baseline','system',%s)
    """,(version,json.dumps({"reference_count":len(verified)})))
    return reference_versions.current(db)
