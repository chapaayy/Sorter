"""Single PostgreSQL registry of observed paths, ownership and physical evidence."""
from __future__ import annotations
import os,re,stat
from pathlib import Path
from string import Formatter
from app import config
from app.storage.categories import CATEGORIES,Category
from app.storage.paths import _field,_check_prefix,uuid_key
from ..database import connect

# Compile the actual contract, not a second path layout.
def _patterns():
    patterns=[]
    for category,spec in CATEGORIES.items():
        template=spec["path"]
        if not template.startswith("app/"):continue
        base=template.rstrip("/")
        pattern="".join(re.escape(lit)+(f"(?P<{field}>[^/]+)" if field else "")
                         for lit,field,_,_ in Formatter().parse(base))
        if template.endswith("/"):pattern+="/.+"
        patterns.append((len(base),category,spec,re.compile(pattern)))
    return sorted(patterns,key=lambda row:-row[0])
PATTERNS=_patterns()
ALL_TOKEN=__import__("hashlib").sha256(b"all").hexdigest()[:12]

def classify(key):
    for _,category,spec,pattern in PATTERNS:
        match=pattern.fullmatch(key)
        if not match:continue
        fields=match.groupdict()
        try:
            for name,value in fields.items():_field(name,value)
            _check_prefix(fields)
            if category in (Category.TRANSCODE_TEMP,Category.MODEL_DOWNLOAD):uuid_key(fields["task_id"])
        except ValueError:continue
        if category in (Category.ARCHIVE_LOCK,Category.ZIP_FRAGMENT,Category.ZIP_RESULTS,Category.ZIP_CONSTRUCTION,Category.ZIP_REFERENCES):
            name=key.rsplit("/",1)[-1]
            if re.fullmatch(r"(?:[a-f0-9]{64}|[a-f0-9]{12}-[a-f0-9]{20})\.lock",name):category=Category.ARCHIVE_LOCK
            elif re.fullmatch(r"\.(?:archive|references)-[A-Za-z0-9_-]+\.tmp",name):category=Category.ZIP_FRAGMENT
            elif key.startswith("app/temporary/archives/results/") and re.fullmatch(r"[a-f0-9]{12}-[a-f0-9]{20}\.zip",name):
                category=Category.ZIP_RESULTS if name.startswith(ALL_TOKEN+"-") else Category.ZIP_CONSTRUCTION
            elif key.startswith("app/temporary/archives/references/") and re.fullmatch(r"[a-f0-9]{64}\.zip",name):category=Category.ZIP_REFERENCES
            else:continue
            # Generic archive fragments and locks also carry run ownership.
            if key.startswith("app/temporary/archives/results/"):
                try:fields["run_id"]=_field("run_id",key.split("/")[4])
                except ValueError:continue
        if category==Category.ATOMIC_FRAGMENT and not key.endswith("/fragment"):category=Category.SCRATCH
        if category==Category.REFERENCE_GALLERY:return "unknown","unknown",fields,"unexpected_gallery_file"
        return category.value,CATEGORIES[category]["scope"],fields,None
    return "unknown","unknown",{},"unclassified_path"

def key_for(path,root=None):
    root=Path(root or config.APP_STORAGE_ROOT)
    path=Path(path)
    if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(root) or path==root:return None
    return "app/"+path.relative_to(root).as_posix()

def note(paths,*,subtree=False,db=None):
    keys=sorted({key for path in paths if (key:=key_for(path))})
    if not keys:return
    if db is None:
        with connect() as conn:note(paths,subtree=subtree,db=conn)
        return
    with db.cursor() as cur:
        cur.executemany("""INSERT INTO storage_dirty(path,subtree) VALUES(%s,%s)
          ON CONFLICT(path) DO UPDATE SET subtree=storage_dirty.subtree OR excluded.subtree,
          revision=storage_dirty.revision+1,touched_at=clock_timestamp()""",[(k,subtree) for k in keys])

def stat_key(root,key):
    """No symlink ancestors; the leaf itself is evidence, never followed."""
    parts=key.split("/")
    if parts[0]!="app" or len(parts)<2 or any(p in ("",".","..") for p in parts):raise ValueError("Unsafe registry key")
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    fd=os.open(root,flags)
    try:
        for part in parts[1:-1]:
            child=os.open(part,flags,dir_fd=fd);os.close(fd);fd=child
        return os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)
    finally:os.close(fd)

def observe(db,root,keys,generation=None):
    """Small batches. Metadata ownership is authoritative, path labels are not."""
    pending=[];missing=[];unreadable=[]
    for key in dict.fromkeys(keys):
        try:key.encode("utf8")
        except UnicodeEncodeError:continue
        try:st=stat_key(root,key)
        except (FileNotFoundError,NotADirectoryError):
            missing.append(key)
            continue
        except OSError:
            unreadable.append(key)
            continue
        if stat.S_ISDIR(st.st_mode):
            missing.append(key);continue
        category,scope,fields,issue=classify(key)
        kind="file" if stat.S_ISREG(st.st_mode) else "symlink" if stat.S_ISLNK(st.st_mode) else "other"
        if kind!="file" and not (kind=="symlink" and category=="technical_cache"):
            issue="unexpected_"+kind
        pending.append((key,st,category,scope,fields,issue,kind))
    if missing:db.execute("DELETE FROM storage_files WHERE path=ANY(%s)",(missing,))
    if unreadable:db.execute("UPDATE storage_files SET issue='unreadable' WHERE path=ANY(%s)",(unreadable,))
    if not pending:return 0
    tasks=[p[4]["task_id"] for p in pending if p[2]=="transcode_temp"]
    task_rows={str(r["id"]):str(r["batch_id"]) for r in db.execute("SELECT id,batch_id FROM uploads WHERE id=ANY(%s::uuid[])",(tasks,))}
    batches={p[4]["batch_uuid"] for p in pending if "batch_uuid" in p[4]}
    batches.update(task_rows.values())
    runs={p[4]["run_id"] for p in pending if "run_id" in p[4]}
    run_rows={r["id"]:r for r in db.execute("SELECT j.id,j.batch_id,b.owner_id FROM jobs j JOIN batches b ON b.id=j.batch_id WHERE j.id=ANY(%s)",(list(runs),))}
    batches.update(str(r["batch_id"]) for r in run_rows.values())
    batch_rows={str(r["id"]):r["owner_id"] for r in db.execute("SELECT id,owner_id FROM batches WHERE id=ANY(%s::uuid[])",(list(batches),))}
    owner_ids={int(p[4]["user_id"]) for p in pending if "user_id" in p[4]}
    owners={r["id"] for r in db.execute("SELECT id FROM users WHERE id=ANY(%s::bigint[])",(list(owner_ids),))}
    uploads={str(r["id"]):r for r in db.execute("SELECT id,batch_id,target_path,media_output_path,declared_size,finalized FROM uploads WHERE id=ANY(%s::uuid[])",([p[4]["upload_uuid"] for p in pending if "upload_uuid" in p[4] and p[2] in ("fo_original","fo_normalized","fo_upload_part")],))}
    hashes=[p[4]["sha256"] for p in pending if p[2]=="reference_object"]
    refs={r["source_hash"]:r["declared_size"] for r in db.execute("SELECT source_hash,declared_size FROM reference_physical_objects WHERE source_hash=ANY(%s)",(hashes,))}
    embeddings={(r["source_hash"],r["model_signature"]):r["cache_path"] for r in db.execute(
        "SELECT source_hash,model_signature,cache_path FROM reference_cache WHERE source_hash=ANY(%s)",
        ([p[4]["sha256"] for p in pending if p[2]=="reference_embedding"],))}
    ref_parts={(str(r["session_id"]),str(r["upload_id"])) for r in db.execute(
        "SELECT session_id,upload_id FROM reference_import_files WHERE upload_id=ANY(%s::uuid[])",
        ([p[4]["upload_uuid"] for p in pending if p[2]=="reference_upload_part"],))}
    values=[]
    for key,st,category,scope,fields,issue,kind in pending:
        user=int(fields["user_id"]) if "user_id" in fields else None
        batch=fields.get("batch_uuid");run=fields.get("run_id")
        if category=="transcode_temp":batch=task_rows.get(fields["task_id"])
        if category=="reference_upload_part" and (fields["session_uuid"],fields["upload_uuid"]) not in ref_parts:issue=issue or "orphan_reference_upload"
        if run:
            row=run_rows.get(run)
            if row:
                actual=str(row["batch_id"])
                if batch and batch!=actual:issue="run_batch_mismatch"
                else:batch=actual
            elif scope=="personal":issue="orphan_run"
        if batch:
            actual=batch_rows.get(batch)
            if actual is None:issue=issue or "orphan_batch"
            elif user is not None and actual!=user:issue="owner_mismatch"
            elif user is None:user=actual
        if "user_id" in fields and int(fields["user_id"]) not in owners:issue=issue or "orphan_owner"
        if category in ("fo_original","fo_normalized","fo_upload_part"):
            row=uploads.get(fields.get("upload_uuid"))
            if not row or str(row["batch_id"])!=batch:issue=issue or "orphan_upload"
            elif category!="fo_upload_part":
                expected=row["target_path"] if category=="fo_original" else row["media_output_path"]
                if expected!=str(root/key[4:]):issue=issue or "unpublished_or_unexpected_path"
                elif category=="fo_original" and st.st_size!=row["declared_size"]:issue="size_mismatch"
        if category=="reference_object":
            size=refs.get(fields["sha256"])
            if size is None:issue=issue or "orphan_reference"
            elif size!=st.st_size:issue="size_mismatch"
        if category=="reference_embedding" and embeddings.get((fields["sha256"],fields["model_signature"]))!=str(root/key[4:]):
            issue=issue or "orphan_or_mismatched_embedding"
        values.append((key,category,scope,user,batch,run,st.st_dev,st.st_ino,st.st_size,
                       st.st_blocks*512,st.st_nlink,st.st_mtime_ns,st.st_ctime_ns,kind,issue,generation))
    if values:
        with db.cursor() as cur:
            cur.executemany("""INSERT INTO storage_files(path,category,scope,owner_id,batch_id,run_id,device,inode,
             logical_bytes,allocated_bytes,links,mtime_ns,ctime_ns,kind,issue,seen_generation)
             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
             ON CONFLICT(path) DO UPDATE SET category=excluded.category,scope=excluded.scope,owner_id=excluded.owner_id,
             batch_id=excluded.batch_id,run_id=excluded.run_id,device=excluded.device,inode=excluded.inode,
             logical_bytes=excluded.logical_bytes,allocated_bytes=excluded.allocated_bytes,links=excluded.links,
             mtime_ns=excluded.mtime_ns,ctime_ns=excluded.ctime_ns,kind=excluded.kind,issue=excluded.issue,
             seen_generation=coalesce(excluded.seen_generation,storage_files.seen_generation),observed_at=clock_timestamp()
             WHERE (storage_files.category,storage_files.scope,storage_files.owner_id,storage_files.batch_id,
             storage_files.run_id,storage_files.device,storage_files.inode,storage_files.logical_bytes,
             storage_files.allocated_bytes,storage_files.links,storage_files.mtime_ns,storage_files.ctime_ns,
             storage_files.kind,storage_files.issue,storage_files.seen_generation) IS DISTINCT FROM
             (excluded.category,excluded.scope,excluded.owner_id,excluded.batch_id,excluded.run_id,excluded.device,
             excluded.inode,excluded.logical_bytes,excluded.allocated_bytes,excluded.links,excluded.mtime_ns,
             excluded.ctime_ns,excluded.kind,excluded.issue,coalesce(excluded.seen_generation,storage_files.seen_generation))""",values)
    return len(values)
