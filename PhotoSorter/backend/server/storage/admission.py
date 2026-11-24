"""Admission over the existing registry and durable transfer receipts.

One PostgreSQL transaction lock serializes budget changes, receipt creation,
registry handoff and transient leases. It is never held over network or codec
work. The registry is the sole file-byte ledger. No request-time tree scan.
"""
from __future__ import annotations
import os
from fastapi import HTTPException
from app import config
from ..database import connect
from ..services import disk_guard
from .registry import stat_key,key_for

LOCK=723409192
GIB=1024**3

def lock(db):
    db.execute("SELECT pg_advisory_xact_lock(%s)",(LOCK,))

def policy(db):
    return db.execute("SELECT personal_enabled,temporary_limit_bytes,disk_reserve_bytes FROM storage_limits").fetchone()

def block_size(path=None):
    return max(512,os.statvfs(path or config.APP_STORAGE_ROOT).f_frsize)

def rounded(n,path=None):
    n=max(0,int(n))
    block=block_size(path)
    return ((n+block-1)//block)*block

def _actual(key):
    try:
        st=stat_key(config.APP_STORAGE_ROOT,key)
        return st.st_blocks*512
    except (OSError,ValueError):
        return 0

def _receipt_rows(db):
    return db.execute("""SELECT 'fo_upload' AS kind,b.owner_id,u.declared_size,
       'app/temporary/uploads/fo/'||u.batch_id::text||'/'||u.id::text||'.part' AS work_key
      FROM uploads u JOIN batches b ON b.id=u.batch_id WHERE u.kind='fo' AND NOT u.finalized
      UNION ALL SELECT 'reference_upload',NULL,f.declared_size,
       'app/temporary/uploads/references/'||f.session_id::text||'/'||f.upload_id::text||'.part'
      FROM reference_import_files f JOIN reference_import_sessions s ON s.id=f.session_id
      WHERE f.state='pending' AND s.upload_state='uploading' AND (f.storage_admitted OR f.received>0)""").fetchall()

def counters(db):
    """Fresh DB evidence, not the periodic UI snapshot. Credits are bounded by
    the reservation and observed physical blocks. Disk credits require a live
    stat of the exact registered path; no recursive filesystem enumeration.
    """
    temp=db.execute("""SELECT coalesce(sum(physical_bytes),0)::bigint AS n
      FROM storage_accounted_files WHERE scope='temporary'""").fetchone()["n"]
    owners={r["owner_id"]:{"used_bytes":r["n"],"reserved_bytes":0} for r in db.execute(
        "SELECT owner_id,coalesce(sum(charged_bytes),0)::bigint AS n FROM storage_accounted_files WHERE scope='personal' AND owner_id IS NOT NULL GROUP BY owner_id")}
    pending=_receipt_rows(db)
    leases=db.execute("SELECT * FROM storage_reservations").fetchall()
    exact_keys=[r["work_key"] for r in [*pending,*leases] if r["work_key"] and not r.get("work_tree")]
    exact={r["path"]:r["physical_bytes"] for r in db.execute(
        "SELECT path,physical_bytes FROM storage_accounted_files WHERE scope='temporary' AND path=ANY(%s)",(exact_keys,))}
    for row in pending:
        amount=rounded(row["declared_size"])
        row.update(requested_bytes=amount,temporary_bytes=amount,personal_bytes=amount if row["owner_id"] is not None else 0,
                   work_tree=False,publish_keys=[])
    # Match only an operation's private path, never its enclosing shared cache.
    # Paths may have changed since the snapshot; stale credits are conservative.
    temp_future=disk_future=0
    kinds={}
    for row in [*pending,*leases]:
        requested=int(row["requested_bytes"])
        temporary=int(row["temporary_bytes"])
        personal=int(row["personal_bytes"])
        key=row["work_key"]
        seen=physical=0
        if key and row["work_tree"]:
            evidence=db.execute("""SELECT path,physical_bytes FROM storage_accounted_files
              WHERE scope='temporary' AND starts_with(path,%s)""",(key+"/",)).fetchall()
            for e in evidence:
                seen+=e["physical_bytes"]
                if e["physical_bytes"]:physical+=min(e["physical_bytes"],_actual(e["path"]))
        elif key:
            seen=exact.get(key,0)
            physical=_actual(key)
        disk_remaining=max(0,requested-physical)
        temp_remaining=max(0,temporary-seen)
        temp_future+=temp_remaining;disk_future+=disk_remaining
        if row["owner_id"] is not None and personal:
            own=owners.setdefault(row["owner_id"],{"used_bytes":0,"reserved_bytes":0})
            own["reserved_bytes"]+=personal
        bucket=kinds.setdefault(row["kind"],{"bytes":0,"operations":0})
        bucket["bytes"]+=disk_remaining;bucket["operations"]+=1
    return {"temporary_used_bytes":temp,"temporary_reserved_bytes":temp_future,
            "disk_reserved_bytes":disk_future,"owners":owners,"reservations":kinds}

def _ready(db):
    state=db.execute("""SELECT reconciled_at IS NOT NULL AND errors=0 AND
      sampled_at>now()-interval '60 seconds' AS ready FROM storage_accounting_state""").fetchone()
    return bool(state["ready"])

def admit(db,requested,*,temporary=0,owner=None,personal=0,path=None):
    """Caller holds LOCK before creating a receipt or transient reservation."""
    settings=policy(db)
    values=counters(db)
    # Sample free after allocation credits: active append-only producers may
    # allocate more blocks, never credit bytes newer than the free sample.
    total,available=disk_guard.stat(path or config.APP_STORAGE_ROOT)
    guard=disk_guard.reserve(total,configured=settings["disk_reserve_bytes"])
    if available-values["disk_reserved_bytes"]-requested<guard:
        raise HTTPException(507,"Недостаточно места на диске: сохранён системный резерв и место для принятых операций")
    limit=settings["temporary_limit_bytes"]
    if temporary and limit is not None:
        if not _ready(db):raise HTTPException(503,"Учёт хранилища ещё не готов; дождитесь фоновой сверки")
        if values["temporary_used_bytes"]+values["temporary_reserved_bytes"]+temporary>limit:
            raise HTTPException(507,"Недостаточно места во временном хранилище MAP")
    if owner is not None and personal and settings["personal_enabled"]:
        user=db.execute("SELECT storage_limit_bytes FROM users WHERE id=%s",(owner,)).fetchone()
        if not user:raise HTTPException(409,"Владелец данных не найден")
        limit=user["storage_limit_bytes"]
        if limit is not None:
            if not _ready(db):raise HTTPException(503,"Учёт хранилища ещё не готов; дождитесь фоновой сверки")
            current=values["owners"].get(owner,{"used_bytes":0,"reserved_bytes":0})
            if current["used_bytes"]+current["reserved_bytes"]+personal>limit:
                raise HTTPException(507,"Недостаточно места в личной квоте владельца")

def _budget(used,reserved,limit,enabled=True):
    effective=limit if enabled else None
    committed=used+reserved
    return {"used_bytes":used,"reserved_bytes":reserved,"limit_bytes":limit,
            "enabled":enabled and limit is not None,
            "available_bytes":None if effective is None else max(0,effective-committed),
            "state":"unlimited" if effective is None else "exceeded" if committed>effective else "full" if committed==effective else "warning" if committed*10>=effective*9 else "ok"}

def account_budget(db,owner,values=None,settings=None):
    values=counters(db) if values is None else values
    settings=policy(db) if settings is None else settings
    user=db.execute("SELECT storage_limit_bytes FROM users WHERE id=%s",(owner,)).fetchone()
    if not user:raise HTTPException(404,"Аккаунт не найден")
    row=values["owners"].get(owner,{"used_bytes":0,"reserved_bytes":0})
    return _budget(row["used_bytes"],row["reserved_bytes"],user["storage_limit_bytes"],settings["personal_enabled"])

def status(db=None):
    if db is None:
        with connect() as conn:return status(conn)
    settings=policy(db);values=counters(db)
    total,free=disk_guard.stat(config.APP_STORAGE_ROOT)
    baseline=disk_guard.reserve(total,configured=None)
    guard=disk_guard.reserve(total,configured=settings["disk_reserve_bytes"])
    return {"policy":settings,"registry_ready":_ready(db),"total_bytes":total,
            "disk":{"used_bytes":total-free,"free_bytes":free,"reserved_bytes":values["disk_reserved_bytes"],
                    "minimum_bytes":guard,"baseline_bytes":baseline,
                    "available_bytes":max(0,free-guard-values["disk_reserved_bytes"])},
            "temporary":_budget(values["temporary_used_bytes"],values["temporary_reserved_bytes"],settings["temporary_limit_bytes"])}

def configure(values):
    with connect() as db:
        lock(db)
        total,_=disk_guard.stat(config.APP_STORAGE_ROOT)
        for name in ("disk_reserve_bytes","temporary_limit_bytes"):
            if values[name] is not None and not 0<=values[name]<=total:
                raise HTTPException(422,"Лимит должен быть в пределах ёмкости диска")
        if values["personal_enabled"] or values["temporary_limit_bytes"] is not None:
            if not _ready(db):raise HTTPException(409,"Сначала дождитесь полной фоновой сверки")
        db.execute("""UPDATE storage_limits SET personal_enabled=%s,temporary_limit_bytes=%s,disk_reserve_bytes=%s""",
                   (values["personal_enabled"],values["temporary_limit_bytes"],values["disk_reserve_bytes"]))
        return status(db)

def set_account(owner,limit):
    with connect() as db:
        lock(db)
        total,_=disk_guard.stat(config.APP_STORAGE_ROOT)
        if limit is not None and not 0<=limit<=total:raise HTTPException(422,"Лимит должен быть в пределах ёмкости диска")
        if not db.execute("UPDATE users SET storage_limit_bytes=%s WHERE id=%s RETURNING id",(limit,owner)).fetchone():
            raise HTTPException(404,"Аккаунт не найден")
        return account_budget(db,owner)
