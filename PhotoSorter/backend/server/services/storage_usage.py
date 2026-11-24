"""Compatibility usage response sourced exclusively from the registry and host report."""
import json
from pathlib import Path
from app.storage.categories import LOG_BUDGETS_MIB
from ..database import connect
from ..storage.accounting import snapshot,disk
from ..storage.reporting import legacy_categories

def _host(name):
    try:return json.loads((Path("/run/map-updater")/name).read_text())
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
    journal=_host("log-usage.json")
    journals={"at":journal.get("at"),"services":{name:{"bytes":journal.get("services",{}).get(name,{}).get("bytes"),
                  "budget_bytes":n*1024*1024,"partial":journal.get("services",{}).get(name,{}).get("partial",True)}
                  for name,n in LOG_BUDGETS_MIB.items()}}
    db_size=None
    try:
        with connect() as db:db_size=db.execute("SELECT pg_database_size(current_database()) AS bytes").fetchone()["bytes"]
    except Exception:pass
    devices=dict(host.get("filesystems",{}))
    key=str(capacity["device"])
    devices[key]={**devices.get(key,{}),**capacity}
    for device,fs in devices.items():
        app_bytes=data.get("devices",{}).get(device,{}).get("allocated_bytes",0)
        host_bytes=host.get("devices",{}).get(device,{}).get("allocated_bytes",0)
        fs["map_allocated_bytes"]=app_bytes+host_bytes
        fs["outside_map_or_unexplained_bytes"]=fs["used_bytes"]-fs["map_allocated_bytes"]
    groups["logs"]=sum(v.get("allocated_bytes",0) for k,v in host.get("categories",{}).items() if k in ("service_log","run_log","access_log","audit_event"))
    return {"journals":journals,"disk":capacity,"filesystems":devices,"categories_bytes":groups,
      "registry":data,"host":host or None,"database_estimated_bytes":db_size,
      "not_scanned":["Docker shared layers and system files not assigned to MAP","Directory/filesystem metadata","Unlinked-open files are sampled separately"],
      "counting":"registry_physical_inode_deduplicated"}
