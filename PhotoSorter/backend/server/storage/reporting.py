"""Read-only adapters to the one registry. No filesystem walks in HTTP handlers."""
from datetime import datetime,timezone
from app import config
from ..database import connect
from .accounting import SUMS,snapshot,aggregate,missing_keys
from app.storage.categories import CATEGORIES,Category

# Stable legacy response labels; stage 8 can consume native category IDs.
LEGACY={
 "fo_original":"originals","fo_normalized":"normalized","result_media":"results_files","result_metadata":"results_files",
 "fo_thumbnail":"thumbnails","reference_object":"reference_objects","reference_gallery":"reference_gallery",
 "reference_thumbnail":"reference_thumbnails","reference_embedding":"reference_cache","fo_upload_part":"incoming",
 "reference_upload_part":"reference_uploads","zip_results":"results_zip","zip_construction":"results_zip",
 "zip_references":"references_zip","technical_cache":"other_cache","run_state":"runs",
 "model_weights":"models","model_source":"models","model_metadata":"models","unknown":"other",
}
for category,spec in CATEGORIES.items():
    if category.value not in LEGACY:LEGACY[category.value]="results_temporary" if spec["scope"]=="temporary" else "other"
def counter():
    return {"files":0,"logical_bytes":0,"allocated_bytes":0,"charged_bytes":0,"hardlink_paths":0,"hardlink_reused_bytes":0}
def merge(dest,src):
    for key in dest:dest[key]+=src.get(key,0)
def legacy_categories(categories):
    groups={}
    for name,row in categories.items():merge(groups.setdefault(LEGACY.get(name,"other"),counter()),row)
    return groups

def expected_missing(db,limit=100,offset=0):
    query,params=missing_keys()
    return db.execute(query+"""SELECT path,'expected_not_observed' AS issue
      FROM missing ORDER BY path LIMIT %s OFFSET %s""",(*params,limit,offset)).fetchall()

def issues(limit=100,offset=0):
    with connect() as db:
        rows=db.execute("""SELECT path,category,owner_id,batch_id,run_id,issue,logical_bytes,allocated_bytes
          FROM storage_files WHERE issue IS NOT NULL ORDER BY path LIMIT %s OFFSET %s""",(limit,offset)).fetchall()
        missing=expected_missing(db,limit,offset)
    return {"files":rows,"missing":missing,"offset":offset,"limit":limit,"snapshot":snapshot().get("sampled_at")}

def history(db):
    # Retained member dependency graph, registry bytes only. Never rescan media.
    row=db.execute("""WITH history AS (
      SELECT DISTINCT m.source_hash FROM reference_version_members m
      WHERE NOT EXISTS(SELECT 1 FROM reference_library_state s JOIN reference_version_members c
       ON c.version_id=s.current_version_id WHERE c.source_hash=m.source_hash)
      AND NOT EXISTS(SELECT 1 FROM uploads u WHERE u.kind='reference' AND u.finalized AND u.checksum=m.source_hash)
      AND NOT EXISTS(SELECT 1 FROM reference_import_files f JOIN reference_import_sessions s ON s.id=f.session_id
       WHERE f.checksum=m.source_hash AND s.upload_state<>'cancelled' AND s.preparation_state NOT IN ('completed','stopped'))
    ), evidence AS (
      SELECT f.category,f.physical_bytes FROM storage_accounted_files f
      JOIN history h ON h.source_hash=replace(split_part(f.path,'/',array_length(string_to_array(f.path,'/'),1)),'.npy','')
      WHERE f.category IN ('reference_object','reference_embedding'))
      SELECT count(*) FILTER(WHERE category='reference_object') AS objects,
       coalesce(sum(physical_bytes) FILTER(WHERE category='reference_object'),0)::bigint AS object_bytes,
       count(*) FILTER(WHERE category='reference_embedding') AS embeddings,
       coalesce(sum(physical_bytes) FILTER(WHERE category='reference_embedding'),0)::bigint AS embedding_bytes
      ,(SELECT count(*) FROM history h WHERE NOT EXISTS
          (SELECT 1 FROM storage_files f WHERE f.category='reference_object'
           AND split_part(f.path,'/',array_length(string_to_array(f.path,'/'),1))=h.source_hash))
       +(SELECT count(*) FROM reference_cache c JOIN history h ON h.source_hash=c.source_hash
          WHERE NOT EXISTS (SELECT 1 FROM storage_files f WHERE f.path='app/'||substr(c.cache_path,%s))) AS missing
      FROM evidence""",(len(str(config.APP_STORAGE_ROOT))+2,)).fetchone()
    row["partial"]=bool(row["missing"])
    return row

def breakdown():
    data=snapshot()
    metrics=("originals","normalized","results_files","results_zip","results_temporary")
    with connect() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        live=aggregate(db)
        data.update(live)
        groups=legacy_categories(live["categories"])
        rows=db.execute("""WITH top_batches AS (
            SELECT batch_id,sum(physical_bytes) AS bytes FROM storage_accounted_files
            WHERE batch_id IS NOT NULL GROUP BY batch_id ORDER BY bytes DESC,batch_id LIMIT 50)
            SELECT f.batch_id::text,b.display_name,f.category,"""+SUMS+"""
            FROM storage_accounted_files f JOIN top_batches t ON t.batch_id=f.batch_id
            LEFT JOIN batches b ON b.id=f.batch_id GROUP BY f.batch_id,b.display_name,f.category""").fetchall()
        total=db.execute("SELECT count(DISTINCT batch_id) AS n FROM storage_files").fetchone()["n"]
        historical=history(db)
    batches={}
    for row in rows:
        ident=row.pop("batch_id");name=row.pop("display_name");category=LEGACY.get(row.pop("category"),"other")
        item=batches.setdefault(ident,{"batch_id":ident,"display_name":name or ident,**counter(),**{m:counter() for m in metrics}})
        for k in counter():item[k]+=row[k]
        if category in metrics:merge(item[category],row)
    ordered=sorted(batches.values(),key=lambda x:(-x["allocated_bytes"],x["batch_id"]))
    return {"categories":groups,"batches":ordered,"total_batches":total,"unlisted_batches":max(0,total-len(ordered)),
       "files_scanned":sum(x["files"] for x in groups.values()),"hardlink_paths":sum(x["hardlink_paths"] for x in groups.values()),
       "hardlink_reused_bytes":sum(x["hardlink_reused_bytes"] for x in groups.values()),"allocated_total_bytes":data.get("allocated_bytes",0),
       "scan_seconds":0,"partial":data["partial"],"skipped_paths":data["errors"],"captured_at":data.get("sampled_at") or datetime.now(timezone.utc).isoformat(),
       "basis":"registry_st_blocks_512_inode_deduplicated","batch_metadata_available":True,"reference_history":historical}

def inventory(limit=25000):
    # Compatibility snapshot is only a bounded copy of registry rows for
    # existing CSV pagination, not a second disk census.
    data=snapshot()
    with connect() as db:
        rows=db.execute("""SELECT f.path,f.category,f.scope,f.owner_id,f.batch_id::text,f.run_id,f.logical_bytes,
            f.physical_bytes AS allocated_bytes,f.physical_rank>1 AS hardlink,f.links,f.mtime_ns,f.issue,
            b.display_name AS owner_name FROM storage_accounted_files f LEFT JOIN batches b ON b.id=f.batch_id
            ORDER BY f.physical_bytes DESC,f.path LIMIT %s""",(limit+1,)).fetchall()
    partial=len(rows)>limit or data["partial"];entries=[]
    groups={}
    for row in rows[:limit]:
        cat=LEGACY.get(row["category"],"other")
        owner=row["batch_id"] or (str(row["owner_id"]) if row["owner_id"] is not None else None)
        purpose={"personal":"permanent","shared":"permanent","temporary":"temporary","protected":"system","system":"system","unknown":"unknown"}.get(row["scope"],"system")
        item={"path":"storage/"+row["path"],"category":cat,"registry_category":row["category"],"purpose":purpose,
              "owner_kind":"batch" if row["batch_id"] else "user" if owner else "shared" if row["scope"]=="shared" else "system",
              "owner_id":owner,"owner_name":row["owner_name"],"logical_bytes":row["logical_bytes"],"allocated_bytes":row["allocated_bytes"],
              "hardlink":row["hardlink"],"links":row["links"],"issue":row["issue"],
              "modified_at":datetime.fromtimestamp(row["mtime_ns"]/1e9,timezone.utc).isoformat()}
        entries.append(item)
        group=groups.setdefault(cat,counter());group["files"]+=1;group["logical_bytes"]+=item["logical_bytes"];group["allocated_bytes"]+=item["allocated_bytes"];group["hardlink_paths"]+=int(item["hardlink"])
    import uuid
    return {"snapshot_id":str(uuid.uuid4()),"captured_at":data.get("sampled_at") or datetime.now(timezone.utc).isoformat(),
       "files_scanned":len(entries),"allocated_bytes":sum(x["allocated_bytes"] for x in groups.values()),
       "logical_bytes":sum(x["logical_bytes"] for x in groups.values()),"categories":groups,"skipped_paths":data["errors"],
       "partial":partial,"scan_seconds":0,"checked_roots":["registry:app"],"not_scanned":["Host-protected categories are aggregated separately","Docker and filesystem metadata are separate"],"batch_metadata_available":True,"description":"Registry snapshot, no filesystem scan"},entries
