"""Compatibility usage response sourced exclusively from the registry and host report."""
import json
from datetime import datetime,timezone
from pathlib import Path
from app.storage.categories import LOG_BUDGETS_MIB
from ..database import connect
from ..storage.accounting import snapshot,disk
from ..storage.reporting import legacy_categories

def _host(name):
    try:
        data=json.loads((Path("/run/map-updater")/name).read_text())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError,TypeError):return {}

def usage():
    data=snapshot();capacity=disk()
    groups={key:0 for key in ("photos","results","incoming","thumbnails","reference_thumbnails","references","reference_cache","reference_uploads","models","logs","runs","other")}
    mapping={"originals":"photos","normalized":"photos","results_files":"results","results_zip":"results",
             "results_temporary":"results","references_zip":"results","reference_objects":"references","reference_gallery":"references",
             "reference_other":"references","other_cache":"models"}
    for name,row in legacy_categories(data.get("categories",{})).items():
        key=mapping.get(name,name)
        groups[key if key in groups else "other"]+=row["allocated_bytes"]
    host=_host("storage-host.json")
    if host:
        try:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(host["at"])).total_seconds()
        except (KeyError,TypeError,ValueError):age=None
        host["sample_age_seconds"]=age
        host["stale"]=age is None or age>180 or age< -60
    journal=_host("log-usage.json")
    journals={"at":journal.get("at"),"services":{name:{"bytes":journal.get("services",{}).get(name,{}).get("bytes"),
                  "budget_bytes":n*1024*1024,"partial":journal.get("services",{}).get(name,{}).get("partial",True)}
                  for name,n in LOG_BUDGETS_MIB.items()}}
    db_size=None
    pg=None
    try:
        with connect() as db:
            db_size=db.execute("SELECT pg_database_size(current_database()) AS bytes").fetchone()["bytes"]
            pg=db.execute("""SELECT count(*) FILTER(WHERE xact_start IS NOT NULL) AS open_transactions,
              count(*) FILTER(WHERE now()-xact_start>interval '5 minutes') AS long_transactions,
              coalesce(max(extract(epoch FROM now()-xact_start)),0)::double precision AS oldest_transaction_seconds
              FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()""").fetchone()
            pg.update(db.execute("""SELECT coalesce(sum(n_dead_tup),0)::bigint AS estimated_dead_tuples,
              coalesce(sum(autovacuum_count),0)::bigint AS autovacuum_count,max(last_autovacuum) AS last_autovacuum
              FROM pg_stat_user_tables""").fetchone())
            if pg["last_autovacuum"]:pg["last_autovacuum"]=pg["last_autovacuum"].isoformat()
            pg["sampled_at"]=datetime.now(timezone.utc).isoformat()
    except Exception:pg=None
    devices=dict(host.get("filesystems",{}))
    key=str(capacity["device"])
    devices[key]={**devices.get(key,{}),**capacity}
    for device,fs in devices.items():
        app_bytes=data.get("devices",{}).get(device,{}).get("allocated_bytes",0)
        host_bytes=host.get("devices",{}).get(device,{}).get("allocated_bytes",0)
        fs["map_allocated_bytes"]=app_bytes+host_bytes if data.get("sampled_at") or host.get("at") else None
        fs["outside_map_or_unexplained_bytes"]=fs["used_bytes"]-fs["map_allocated_bytes"] if fs["map_allocated_bytes"] is not None else None
    groups["logs"]=sum(v.get("allocated_bytes",0) for k,v in host.get("categories",{}).items() if k in ("service_log","run_log","access_log","audit_event"))
    return {"journals":journals,"disk":capacity,"filesystems":devices,"categories_bytes":groups,
      "registry":data,"host":host or None,"database_estimated_bytes":db_size,"postgres_diagnostics":pg,
      "not_scanned":["Docker shared layers and system files not assigned to MAP","Directory/filesystem metadata","Unlinked-open files are sampled separately"],
      "counting":"registry_physical_inode_deduplicated"}
