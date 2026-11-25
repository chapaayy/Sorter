"""Host journal rotation from the same installed storage policy."""
import json
import os
from pathlib import Path
from datetime import datetime,timezone
import fcntl
import re
import stat

def policy(root):
    return json.loads(Path(root).read_text())["log_budgets_mib"]

def record(directory,service,message):
    directory=Path(directory)
    contract=directory.parents[1]/"system/state/log-policy.json"
    budget=policy(contract)[service]
    # Audit events have a separate bounded 90 MiB session within the 100 MiB total.
    if service=="audit":budget=min(10,budget)
    cap=budget*1024*1024//5
    payload=(json.dumps({"at":datetime.now(timezone.utc).isoformat(),"phase":str(message)[:128]})+"\n").encode()
    fd=os.open(directory,os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        name="service.jsonl"
        try:rotate=os.stat(name,dir_fd=fd,follow_symlinks=False).st_size+len(payload)>cap
        except FileNotFoundError:rotate=False
        if rotate:
            for i in range(4,0,-1):
                try:os.replace(name if i==1 else name+"."+str(i-1),name+"."+str(i),src_dir_fd=fd,dst_dir_fd=fd)
                except FileNotFoundError:pass
        h=os.open(name,os.O_CREAT|os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW,0o600,dir_fd=fd)
        try:os.write(h,payload)
        finally:os.close(h)
    finally:os.close(fd)

def prune_postgres(storage,*,budget=None):
    storage=Path(storage)
    with (storage/"system/updater/private/log-prune.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _prune_postgres(storage,budget=budget)

def _prune_postgres(storage,*,budget=None):
    root=storage/"logs/postgres"
    if budget is None:budget=policy(storage/"system/state/log-policy.json")["postgres"]*1024*1024
    active_file=storage/"infrastructure/postgres/data/current_logfiles"
    try:active={Path(row.split(" ",1)[1]).name for row in active_file.read_text().splitlines()}
    except (OSError,ValueError,IndexError):return 0
    if not active:return 0
    files=[]
    for f in root.iterdir():
        if re.fullmatch(r"postgresql-[0-9]{8}-[0-9]{6}\.log",f.name):
            st=f.stat(follow_symlinks=False)
            if stat.S_ISREG(st.st_mode):files.append((st.st_mtime_ns,st.st_size,f))
    total=sum(x[1] for x in files);removed=0
    for _,size,path in sorted(files):
        if total<=budget:break
        # Re-read active file immediately before unlink; only old, closed logs.
        current={Path(row.split(" ",1)[1]).name for row in active_file.read_text().splitlines()}
        if path.name in active|current:continue
        path.unlink(missing_ok=True);total-=size;removed+=1
    return removed

def publish_usage(storage):
    """The protected-host sample also supplies journal-budget usage."""
    storage=Path(storage)
    with (storage/"system/updater/private/host-sample.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _publish_usage(storage)

def _publish_usage(storage):
    contract=json.loads((storage/"system/state/log-policy.json").read_text())
    from host_accounting import measure
    from map_updater import atomic_json
    control=storage/"system/updater/control"
    engine=None
    previous={}
    try:
        previous=json.loads((control/"storage-host.json").read_text())
        sample=datetime.fromisoformat(previous["engine_sampled_at"])
        if (datetime.now(timezone.utc)-sample).total_seconds()<300:
            engine=previous["docker"]
            sampled=previous["engine_sampled_at"]
    except (OSError,ValueError,KeyError,TypeError):pass
    report=measure(storage,contract,engine=engine)
    report["engine_sampled_at"]=sampled if engine is not None else report["at"]
    # WAL is a subset of PGDATA, and change is meaningful only between
    # complete samples. Negative change after checkpoint/recycling is valid.
    report["postgres_wal_delta_bytes"]=None
    if previous and not previous.get("partial",True) and not report["partial"]:
        old_wal=previous.get("postgres_wal_subset_bytes")
        if isinstance(old_wal,int):
            report["postgres_wal_delta_bytes"]=report["postgres_wal_subset_bytes"]-old_wal
            report["previous_host_sample_at"]=previous.get("at")
    # Independent full tree walk at most once per hour; retry incomplete samples
    # after five minutes. Ordinary one-minute journal samples remain bounded.
    from storage_tree import compare
    previous_tree=previous.get("tree_check") or {}
    try:
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(previous_tree["finished_at"])).total_seconds()
    except (KeyError,ValueError,TypeError):age=float("inf")
    interval=3600 if previous_tree.get("comparable") else 300
    report["tree_check"]=previous_tree if 0<=age<interval else compare(storage,report)
    rows=report.pop("journals")
    atomic_json(control/"storage-host.json",report)
    atomic_json(control/"log-usage.json",{"at":report["at"],"services":rows})

def maintenance(storage):
    storage=Path(storage)
    prune_postgres(storage)
    # This is the same lock held by install.sh and the host updater, never a
    # second cleanup system. An active build retains all of its resources.
    from map_updater import recover_owned_work
    lock=storage/"system/updater/private/deploy.lock"
    with lock.open("a") as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:pass
        else:
            recover_owned_work(storage)
    publish_usage(storage)

if __name__=="__main__":
    import sys
    maintenance(Path(sys.argv[1]))
