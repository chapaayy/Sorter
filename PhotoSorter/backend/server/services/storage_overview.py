"""Read-only projection of existing independent measurements; no new accounting."""
def _number(value):
    return type(value) is int and value>=0

def _capacity(row):
    if not isinstance(row,dict):return False
    total,used,available=(row.get(k) for k in ("total_bytes","used_bytes","available_bytes"))
    return all(_number(n) for n in (total,used,available)) and total>0 and used+available<=total

def disk_overview(capacity,host):
    """Prefer paired capacity, never subtract registry totals from the disk.
    Free is physical free, including filesystem-reserved blocks; admission
    continues to use the live available bytes and its existing policy.
    """
    tree=host.get("tree_check") or {}
    result={"total_bytes":capacity["total_bytes"],"used_bytes":capacity["used_bytes"],
            "available_bytes":capacity["available_bytes"],"free_bytes":capacity["total_bytes"]-capacity["used_bytes"],
            "map_bytes":None,"system_bytes":None,"sampled_at":None,"system_details":None}
    measured=tree.get("capacity_after")
    amount=tree.get("allocated_bytes")
    valid=(not host.get("stale",True) and not tree.get("stale",True)
           and not tree.get("partial",True) and tree.get("finished_at")
           and str(tree.get("device"))==str(capacity.get("device"))
           and _capacity(measured) and measured["total_bytes"]==capacity["total_bytes"]
           and _number(amount) and amount<=measured["used_bytes"])
    if valid:
        result.update(total_bytes=measured["total_bytes"],used_bytes=measured["used_bytes"],
                      available_bytes=measured["available_bytes"],free_bytes=measured["total_bytes"]-measured["used_bytes"],
                      map_bytes=amount,system_bytes=measured["used_bytes"]-amount,sampled_at=tree["finished_at"])
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
