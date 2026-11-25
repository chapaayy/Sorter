"""Bounded historical diagnostic samples, persisted in the existing host report."""
def append_sample(previous,key,report,fields,*,limit=336):
    rows=previous.get(key,[])
    if not isinstance(rows,list):rows=[]
    rows=[row for row in rows if isinstance(row,dict) and isinstance(row.get("finished_at"),str)]
    at=report.get("finished_at")
    if isinstance(at,str) and (not rows or rows[-1]["finished_at"]!=at):
        rows.append({"finished_at":at,**{field:report.get(field) for field in fields}})
    return rows[-limit:]

def tree_history(previous,report):
    return append_sample(previous,"tree_history",report,(
        "allocated_bytes","directory_bytes","comparable","unexplained_bytes","absolute_discrepancy_bytes",
        "app_delta_bytes","host_delta_bytes","unknown_bytes","unknown_files"))

def disk_history(previous,report):
    return append_sample(previous,"disk_history",report,(
        "allocated_bytes","residual_bytes","comparable","device"),limit=64)
