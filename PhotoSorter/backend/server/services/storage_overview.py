"""Read-only projection of existing independent measurements; no new accounting."""
def _number(value):
    return type(value) is int and value>=0

def _capacity(row):
    if not isinstance(row,dict):return False
    total,used,available=(row.get(k) for k in ("total_bytes","used_bytes","available_bytes"))
    return all(_number(n) for n in (total,used,available)) and total>0 and used+available<=total

def disk_overview(capacity,host,registry):
    """Live device counters plus the existing minute/registry snapshots.
    Last independent directory blocks and signed reconciliation residual are
    carried explicitly as estimates, never reclassified into system bytes.
    """
    device=str(capacity["device"])
    result={"total_bytes":capacity["total_bytes"],"used_bytes":capacity["used_bytes"],
            "available_bytes":capacity["available_bytes"],"free_bytes":capacity["total_bytes"]-capacity["used_bytes"],
            "map_bytes":None,"system_bytes":None,"sampled_at":capacity.get("sampled_at"),"system_details":None,
            "directory_bytes":None,"directory_sampled_at":None,"adjustment_bytes":None,
            "adjustment_sampled_at":None,"registry_sampled_at":registry.get("sampled_at"),
            "host_sampled_at":host.get("at"),"estimated":True,"preliminary":True}
    tree=host.get("tree_check") or {}
    directories=host.get("directory_sample") or (tree if not tree.get("partial",True) else {})
    adjustment=host.get("discrepancy_sample") or (tree if tree.get("comparable") else {})
    if str(directories.get("device"))==device and _number(directories.get("directory_bytes")):
        result.update(directory_bytes=directories["directory_bytes"],directory_sampled_at=directories.get("finished_at"))
    if str(adjustment.get("device"))==device and type(adjustment.get("unexplained_bytes")) is int:
        result.update(adjustment_bytes=adjustment["unexplained_bytes"],adjustment_sampled_at=adjustment.get("finished_at"))
    app=registry.get("devices")
    infrastructure=host.get("devices")
    if (registry.get("sampled_at") and not registry.get("stale",True) and registry.get("reconciled_at")
        and not registry.get("errors") and host.get("at") and not host.get("stale",True)
        and not host.get("partial",True) and not tree.get("cross_scope_links") and isinstance(app,dict) and isinstance(infrastructure,dict)
        and set(app)<= {device} and set(infrastructure)<= {device}):
        a=app.get(device,{}).get("allocated_bytes",0)
        h=infrastructure.get(device,{}).get("allocated_bytes",0)
        if _number(a) and _number(h):
            amount=a+h+(result["directory_bytes"] or 0)+(result["adjustment_bytes"] or 0)
            if 0<=amount<=capacity["used_bytes"]:
                result.update(map_bytes=amount,system_bytes=capacity["used_bytes"]-amount,
                              sampled_at=capacity.get("sampled_at"),
                              preliminary=bool(registry.get("partial") or result["directory_bytes"] is None or result["adjustment_bytes"] is None))
    # Root diagnostic is a separate observation, with its own denominator.
    # Never subtract its categories from a newer MAP/system total.
    disk=host.get("disk_check") or {}
    root_cap=disk.get("capacity_after")
    root_map=disk.get("map_storage") or {}
    def bucket(row):
        if not isinstance(row,dict):return None
        a,b=row.get("file_bytes"),row.get("directory_bytes")
        return a+b if _number(a) and _number(b) else None
    root_amount=bucket(root_map)
    if (not host.get("stale",True) and not disk.get("stale",True) and disk.get("finished_at")
        and str(disk.get("device"))==str(capacity.get("device")) and _capacity(root_cap)
        and root_cap["total_bytes"]==capacity["total_bytes"]):
        rows={key:bucket(disk.get(key)) for key in ("docker_engine","containerd_default","system_logs")}
        known=sum(n for n in rows.values() if n is not None)
        system=root_cap["used_bytes"]-root_amount if root_amount is not None else None
        complete=bool(disk.get("comparable") and not disk.get("partial",True)
                      and system is not None and system>=known)
        result["system_details"]={"sampled_at":disk["finished_at"],"system_bytes":system if complete else None,
                                  "categories":rows,"remaining_bytes":system-known if complete else None,
                                  "partial":not complete}
    return result
