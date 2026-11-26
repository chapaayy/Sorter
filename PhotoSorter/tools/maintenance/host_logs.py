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

CHECK_COOLDOWN=300

def _age(at):
    try:return (datetime.now(timezone.utc)-datetime.fromisoformat(at)).total_seconds()
    except (ValueError,TypeError):return float("inf")

def _check_state(control):
    try:
        value=json.loads((control/"storage-check.json").read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def _write_check(control,state):
    from map_updater import atomic_json
    atomic_json(control/"storage-check.json",state)

def request_check(storage,*,automatic=False):
    """Queue one fixed, read-only operation for the existing host timer."""
    control=Path(storage)/"system/updater/control"
    with (control.parent/"private/storage-check.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=_check_state(control)
        if not automatic:
            if state.get("state") in ("queued","running","retry"):
                return {"rejected":True,"detail":"Проверка уже запрошена или выполняется"}
            if _age(state.get("finished_at"))<CHECK_COOLDOWN:
                return {"rejected":True,"detail":"Повторная проверка доступна через 5 минут после завершения"}
        # An installation request arriving during a scan must survive that scan.
        from uuid import uuid4
        request={"state":"queued","request_id":uuid4().hex,"requested_at":datetime.now(timezone.utc).isoformat(),
                 "reason":"deployment" if automatic else "manual"}
        _write_check(control,request)
        return request

def _claim_check(control,previous_tree,*,force=False,ready=True):
    with (control.parent/"private/storage-check.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=_check_state(control)
        interval=3600 if previous_tree.get("comparable") else 300
        due=not 0<=_age(previous_tree.get("finished_at"))<interval
        pending=state.get("state") in ("queued","running","retry")
        if not (force or pending or due):return None
        if (not ready and not force) or (control/"maintenance").exists():return None
        if not force and state.get("state")=="retry" and 0<=_age(state.get("finished_at"))<CHECK_COOLDOWN:return None
        from uuid import uuid4
        state={**state,"state":"running","request_id":state.get("request_id") if pending else uuid4().hex,
               "reason":state.get("reason") if pending else "periodic",
               "requested_at":state.get("requested_at") if pending else datetime.now(timezone.utc).isoformat(),
               "started_at":datetime.now(timezone.utc).isoformat()}
        _write_check(control,state)
        return state

def _finish_check(control,claim,tree):
    with (control.parent/"private/storage-check.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=_check_state(control)
        if current.get("request_id")!=claim["request_id"]:return
        complete=bool(tree.get("comparable"))
        _write_check(control,{**claim,"state":"completed" if complete else "retry",
            "finished_at":tree["finished_at"],"detail":None if complete else "Замер неполный или данные менялись; повтор через 5 минут."})

def _baseline(previous,tree):
    # Retain last valid observations across incomplete attempts.
    directories=previous.get("directory_sample")
    adjustment=previous.get("discrepancy_sample")
    for row in (previous.get("tree_check") or {},tree):
        if not row.get("partial",True) and row.get("device") is not None and type(row.get("directory_bytes")) is int:
            directories={k:row.get(k) for k in ("device","finished_at","directory_bytes")}
        if row.get("comparable") and type(row.get("unexplained_bytes")) is int:
            adjustment={k:row.get(k) for k in ("device","finished_at","unexplained_bytes","absolute_discrepancy_bytes")}
    return directories,adjustment

def publish_usage(storage,*,force_check=False):
    """The protected-host sample also supplies journal-budget usage."""
    storage=Path(storage)
    with (storage/"system/updater/private/host-sample.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        return _publish_usage(storage,force_check=force_check)

def _publish_usage(storage,*,force_check=False):
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
    # Publish the minute sample before expensive independent diagnostics.
    from storage_tree import compare,registry_sample
    from storage_check_history import tree_history,disk_history
    previous_tree=previous.get("tree_check") or {}
    report["tree_check"]=previous_tree or None
    for key in ("disk_check","tree_history","disk_history"):
        if key in previous:report[key]=previous[key]
    report["directory_sample"],report["discrepancy_sample"]=_baseline(previous,previous_tree)
    rows=report.pop("journals")
    atomic_json(control/"storage-host.json",report)
    atomic_json(control/"log-usage.json",{"at":report["at"],"services":rows})
    # Avoid Docker exec every minute when no independent check is due.
    state=_check_state(control)
    interval=3600 if previous_tree.get("comparable") else 300
    due=force_check or state.get("state") in ("queued","running","retry") or not 0<=_age(previous_tree.get("finished_at"))<interval
    claim=None
    if due and not (control/"maintenance").exists():
        # A full initial registry pass and a ready API are prerequisites.
        evidence=registry_sample()
        ready=bool(evidence and evidence.get("sampled_at") and evidence.get("reconciled_at") and not evidence.get("stale") and not evidence.get("errors"))
        if not force_check:
            with (control.parent/"private/deploy.lock").open("a") as deploy:
                try:fcntl.flock(deploy,fcntl.LOCK_SH|fcntl.LOCK_NB)
                except BlockingIOError:ready=False
        claim=_claim_check(control,previous_tree,force=force_check,ready=ready)
    if claim:
        try:
            # Publishing the operational snapshot and request status can change
            # the protected host files themselves. Sample that same scope again
            # before comparison rather than measuring against our own old report.
            report["tree_check"]=compare(storage,lambda:measure(
                storage,contract,engine=report["docker"],include_engine=False))
        except Exception:
            report["tree_check"]={"finished_at":datetime.now(timezone.utc).isoformat(),"partial":True,"comparable":False,"errors":1}
        report["directory_sample"],report["discrepancy_sample"]=_baseline(previous,report["tree_check"])
        report["tree_history"]=tree_history(previous,report["tree_check"])
        # Publish the result before completing the request, independently of root diagnostics.
        atomic_json(control/"storage-host.json",report)
        _finish_check(control,claim,report["tree_check"])
    from disk_tree import measure_disk
    old_disk=previous.get("disk_check") or {}
    try:
        disk_age=(datetime.now(timezone.utc)-datetime.fromisoformat(old_disk["finished_at"])).total_seconds()
    except (KeyError,ValueError,TypeError):disk_age=float("inf")
    # Root filesystem scan is separate and less frequent than the MAP tree.
    # A failed/partial census never replaces the live capacity counter.
    disk_interval=21600 if old_disk.get("comparable") else 3600
    if not force_check and 0<=disk_age<disk_interval:
        report["disk_check"]=old_disk
    else:
        try:report["disk_check"]=measure_disk(storage,report["docker"])
        except (OSError,ValueError,TypeError):
            report["disk_check"]={"finished_at":datetime.now(timezone.utc).isoformat(),
                                  "partial":True,"comparable":False,"errors":1}
    report["tree_history"]=tree_history(previous,report["tree_check"] or {})
    report["disk_history"]=disk_history(previous,report["disk_check"])
    atomic_json(control/"storage-host.json",report)

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
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("storage",type=Path)
    parser.add_argument("--sample-only",action="store_true",help="Collect statistics without retention/cleanup")
    parser.add_argument("--force-check",action="store_true",help="Refresh both independent censuses")
    parser.add_argument("--request-check",action="store_true",help="Queue independent MAP check after successful deployment")
    args=parser.parse_args()
    if args.force_check and not args.sample_only:parser.error("--force-check requires --sample-only")
    if args.request_check:request_check(args.storage,automatic=True)
    elif args.sample_only:publish_usage(args.storage,force_check=args.force_check)
    else:maintenance(args.storage)
