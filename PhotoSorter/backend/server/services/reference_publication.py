"""Immutable reference-library versions; a single publication pointer.

An empty V1 is the normal bootstrap for a clean beta installation. Every
following version consists exclusively of checksum-verified staged objects.
"""
from __future__ import annotations
import hashlib
import json
from app.system.model_store import signature
from ..db.repositories import reference_versions as repository
from ..storage import reference_objects

LOCK=723409133

def digest_members(members,model_signature):
    content=[(str(m["reference_id"]),m["sam"],m["source_hash"])
             for m in sorted(members,key=lambda m:(m["sam"],str(m["reference_id"])))]
    return hashlib.sha256(json.dumps([model_signature,content],
        ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def verify_member(member):
    if member["source_kind"]!="staged":
        raise ValueError("Only prepared staged objects may belong to the library")
    reference_objects.verify(member["target_path"],reference_objects.ROOT,
                             member["declared_size"],digest=member["source_hash"])

def ensure_initial_version(db):
    """Create V1 with no references. Importing the first reference is fully legal."""
    db.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK,))
    state=db.execute("""
        SELECT current_version_id FROM reference_library_state WHERE id=1 FOR UPDATE
    """).fetchone()
    if not state:
        raise RuntimeError("reference_library_state schema is missing")
    if state["current_version_id"] is not None:
        incompatible=db.execute("""
            SELECT 1 FROM reference_version_members
            WHERE version_id=%s AND source_kind<>'staged' LIMIT 1
        """,(state["current_version_id"],)).fetchone()
        if incompatible:
            raise RuntimeError(
                "Это база старой бета-версии с прежними образцами. "
                "Для новой архитектуры требуется чистая тестовая установка.")
        return repository.current(db)
    initial_sig=signature()
    version=db.execute("""
        INSERT INTO reference_library_versions(version_number,manifest_digest,model_signature)
        VALUES (1,%s,%s) RETURNING id
    """,(digest_members([],initial_sig),initial_sig)).fetchone()["id"]
    db.execute("""UPDATE reference_library_state
        SET current_version_id=%s,baseline_state='ready',
            baseline_error=NULL,updated_at=now() WHERE id=1""",(version,))
    db.execute("""
        INSERT INTO reference_library_events(version_id,event_kind,details)
        VALUES (%s,'baseline',%s::jsonb)
    """,(version,json.dumps({"reference_count":0})))
    return repository.current(db)

def publish(db,members,model_signature,*,job_id=None,event_kind="reference_prepared"):
    """Run with global FIFO advisory lock + publication row lock, commit atomically."""
    for member in members:
        verify_member(member)
    existing=repository.current(db)
    if not existing or existing["id"] is None:
        raise RuntimeError("Reference library not initialized")
    digest=digest_members(members,model_signature)
    if existing["manifest_digest"]==digest:
        return existing,False
    number=db.execute("""
        SELECT COALESCE(MAX(version_number),0)+1 AS n FROM reference_library_versions
    """).fetchone()["n"]
    version=db.execute("""
        INSERT INTO reference_library_versions(version_number,manifest_digest,
            model_signature,preparation_job_id)
        VALUES (%s,%s,%s,%s) RETURNING id
    """,(number,digest,model_signature,job_id)).fetchone()["id"]
    if members:
        with db.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO reference_version_members(version_id,reference_id,
                    sam,filename,source_hash,target_path,declared_size,source_kind)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'staged')
            """,[(version,m["reference_id"],m["sam"],m["filename"],m["source_hash"],
                  m["target_path"],m["declared_size"]) for m in members])
    db.execute("""UPDATE reference_library_state
        SET current_version_id=%s,baseline_state='ready',
            baseline_error=NULL,updated_at=now() WHERE id=1""",(version,))
    db.execute("""
        INSERT INTO reference_library_events(version_id,event_kind,details)
        VALUES (%s,%s,%s::jsonb)
    """,(version,event_kind,json.dumps({"reference_count":len(members)})))
    return repository.current(db),True

def snapshot(db,version_id):
    entries=repository.members(db,version_id)
    for member in entries:
        verify_member(member)
    return [{"path":m["target_path"],"sam":m["sam"],"hash":m["source_hash"],
             "id":str(m["reference_id"])} for m in entries]
