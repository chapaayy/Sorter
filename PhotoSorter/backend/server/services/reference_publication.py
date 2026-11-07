"""Atomic reference version composition and legacy reconciliation.

The only visibility switch is reference_library_state.current_version_id.
All staged/legacy objects must already exist and be checksum-verified.
"""
from __future__ import annotations
import hashlib
import json
from ..storage import reference_versions as objects
from ..db.repositories import reference_versions as repository

def digest_members(members,model_signature):
    content=[(str(m["reference_id"]),m["sam"],m["source_hash"],m["source_kind"])
             for m in sorted(members,key=lambda x:(x["sam"],str(x["reference_id"])))]
    return hashlib.sha256(json.dumps([model_signature,content],
        ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def publish(db,members,signature,*,job_id=None,event_kind="reference_prepared"):
    """Caller holds scheduling key 133 and state row FOR UPDATE."""
    if not members:
        raise ValueError("Нельзя публиковать пустую библиотеку")
    for item in members:
        objects.verify_member(item)
    existing=repository.current(db)
    digest=digest_members(members,signature)
    if existing and existing["manifest_digest"]==digest:
        return existing,False
    version=db.execute("""
        SELECT COALESCE(MAX(version_number),0)+1 AS n FROM reference_library_versions
    """).fetchone()["n"]
    record=db.execute("""
        INSERT INTO reference_library_versions(version_number,manifest_digest,
                                               model_signature,preparation_job_id)
        VALUES (%s,%s,%s,%s) RETURNING id
    """,(version,digest,signature,job_id)).fetchone()["id"]
    with db.cursor() as cur:
        cur.executemany("""
            INSERT INTO reference_version_members(version_id,reference_id,
                sam,filename,source_hash,target_path,declared_size,source_kind)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,[(record,m["reference_id"],m["sam"],m["filename"],m["source_hash"],
              m["target_path"],m["declared_size"],m["source_kind"]) for m in members])
    db.execute("""
        UPDATE reference_library_state SET current_version_id=%s,
            baseline_state='ready',baseline_error=NULL,updated_at=now() WHERE id=1
    """,(record,))
    db.execute("""
        INSERT INTO reference_library_events(version_id,event_kind,details)
        VALUES (%s,%s,%s::jsonb)
    """,(record,event_kind,json.dumps({"reference_count":len(members)})))
    return repository.current(db),True

def reconcile_legacy(db,*,model_signature):
    """With advisory key 133 already held, sync pre-FIFO legacy edits.

    Stage 1 baseline is metadata-only. The first call migrates it into
    immutable objects and includes any legacy edits made since stage 1.
    """
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    state=repository.current(db)
    if not state or state["baseline_state"]!="ready":
        raise RuntimeError("Базовая версия образцов не проверена")
    prior=repository.members(db,state["id"])
    staged=[dict(m) for m in prior if m["source_kind"]=="staged"]
    source=db.execute("""
        SELECT id,sam,filename,checksum,target_path,declared_size
        FROM uploads u WHERE kind='reference' AND finalized
          AND NOT EXISTS (SELECT 1 FROM reference_import_files f WHERE f.upload_id=u.id)
        ORDER BY sam,id
        FOR SHARE
    """).fetchall()
    legacy=[]
    for row in source:
        stable,digest=objects.stable_legacy(row)
        legacy.append({"reference_id":row["id"],"sam":row["sam"],
            "filename":row["filename"],"source_hash":digest,
            "target_path":str(stable),"declared_size":row["declared_size"],
            "source_kind":"legacy"})
    members=staged+legacy
    if not members:
        raise RuntimeError("Нет готовых образцов")
    old_semantic=sorted((str(m["reference_id"]),m["sam"],m["source_hash"],m["source_kind"]) for m in prior)
    new_semantic=sorted((str(m["reference_id"]),m["sam"],m["source_hash"],m["source_kind"]) for m in members)
    # A model signature change requires a separately prepared version, never
    # silently use old feature vectors from incompatible weights.
    if state["model_signature"] and state["model_signature"]!=model_signature:
        raise RuntimeError("Модель изменилась — сначала нужна повторная подготовка образцов")
    if (old_semantic==new_semantic and
        all(m["target_path"]==n["target_path"]
            for m,n in zip(sorted(prior,key=lambda x:str(x["reference_id"])),
                           sorted(members,key=lambda x:str(x["reference_id"])))) and
        state["model_signature"]==model_signature):
        return state
    # New objects + current version pointer are committed in one transaction.
    # A stage-1 metadata-only V1 conversion is not a new recognition change.
    event="legacy_reconcile" if old_semantic!=new_semantic else "baseline_immutable"
    version,_=publish(db,members,model_signature,event_kind=event)
    return version

def snapshot(db,version_id):
    entries=repository.members(db,version_id)
    for member in entries:
        objects.verify_member(member)
    return [{"path":m["target_path"],"sam":m["sam"],
             "hash":m["source_hash"],"id":str(m["reference_id"])}
            for m in entries]
