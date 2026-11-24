"""Bounded protected-host metadata sample. Never scans Docker layers or app files."""
import json,os,re,stat,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
from string import Formatter

def counters():return {"files":0,"logical_bytes":0,"allocated_bytes":0,"hardlink_paths":0}
def capacity(path):
    st=os.stat(path);fs=os.statvfs(path)
    return str(st.st_dev),{"total_bytes":fs.f_blocks*fs.f_frsize,"used_bytes":(fs.f_blocks-fs.f_bfree)*fs.f_frsize,"available_bytes":fs.f_bavail*fs.f_frsize}
def _rules(contract):
    rows=[]
    for spec in contract["categories"]:
        template=spec["path"]
        if template.startswith(("app/","@")):continue
        pattern="".join(re.escape(lit)+("[^/]+" if field else "") for lit,field,_,_ in Formatter().parse(template.rstrip("/")))
        if template.endswith("/"):pattern+="/.+"
        rows.append((len(template),spec["id"],re.compile(pattern)))
    return sorted(rows,key=lambda r:-r[0])
def _docker(*args):
    return subprocess.check_output(["docker",*args],text=True,timeout=8,stderr=subprocess.DEVNULL).strip()
def engine_metrics():
    result={"available":False,"shared_engine_totals":[],"map_revision_images":[],"limitations":["Docker sizes are engine-wide or per-image virtual sizes, not additive to MAP physical bytes."]}
    try:
        result["root"]=_docker("info","--format","{{.DockerRootDir}}")
        for line in _docker("system","df","--format","{{json .}}").splitlines():
            row=json.loads(line)
            result["shared_engine_totals"].append({k:row[k] for k in ("Type","TotalCount","Active","Size","Reclaimable") if k in row})
        for line in _docker("image","ls","--filter","reference=map-local/app:rev-*","--format","{{json .}}").splitlines():
            row=json.loads(line)
            if re.fullmatch(r"rev-[0-9a-f]{40}",row.get("Tag","")):result["map_revision_images"].append({k:row[k] for k in ("ID","Tag","Size") if k in row})
        result["available"]=True
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return result
def runtime_tmpfs():
    """Only fixed MAP container mounts, read through trusted root /proc.

    These are memory-backed filesystems, never added to disk accounting.
    Multiple containers sharing a mount device are listed but summed once.
    """
    result={"available":False,"partial":True,"mounts":[],"devices":{},
            "basis":"sampled_container_tmpfs_capacity_not_disk"}
    services={"api","worker","cleanup","thumbnail","postgres","caddy"}
    wanted={"/tmp","/var/tmp","/dev/shm"}
    try:
        ids=[c for c in _docker("ps","-q","--filter","label=com.docker.compose.project=outdoor-sorter").splitlines()
             if re.fullmatch(r"[0-9a-f]{12,64}",c)]
        if not ids:return result
        rows=_docker("inspect","--format",'{{.State.Pid}} {{index .Config.Labels "com.docker.compose.service"}}',*ids[:12]).splitlines()
        result["available"]=True
        result["partial"]=len(ids)>12
        for row in rows:
            fields=row.split()
            if len(fields)!=2 or fields[1] not in services or not fields[0].isdigit() or int(fields[0])<=0:continue
            pid,service=fields
            try:
                mountinfo=Path("/proc")/pid/"mountinfo"
                for line in mountinfo.read_text().splitlines():
                    left,right=line.split(" - ",1)
                    mount=left.split()[4]
                    if mount not in wanted or right.split()[0]!="tmpfs":continue
                    dev,info=capacity(Path("/proc")/pid/"root"/mount.lstrip("/"))
                    result["mounts"].append({"service":service,"mount":mount,"device":dev})
                    result["devices"][dev]=info
            except (OSError,ValueError,IndexError):result["partial"]=True
        if not result["mounts"]:result["partial"]=True
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return result

def deleted_open(storage,*,limit=3000,seconds=.5):
    result={"allocated_bytes":0,"logical_bytes":0,"files":0,"partial":True,"basis":"sampled_lower_bound_unlinked_open_app_files"}
    seen=set();count=0
    try:
        device=os.stat(storage/"app").st_dev
        containers=_docker("ps","-q","--filter","label=com.docker.compose.project=outdoor-sorter").splitlines()
        pids=set()
        for container in containers:
            if not re.fullmatch(r"[0-9a-f]{12,64}",container):continue
            for row in _docker("top",container,"-eo","pid").splitlines()[1:]:
                if row.strip().isdigit():pids.add(int(row.strip()))
        deadline=time.monotonic()+seconds
        for pid in sorted(pids):
            try:
                with os.scandir("/proc/"+str(pid)+"/fd") as entries:
                    for entry in entries:
                        count+=1
                        if count>limit or time.monotonic()>deadline:return result
                        try:
                            name=os.readlink(entry.path)
                            if not name.endswith(" (deleted)") or not name.startswith(("/storage/app/",str(storage/"app")+"/")):continue
                            st=os.stat(entry.path)
                            if not stat.S_ISREG(st.st_mode) or st.st_nlink!=0 or st.st_dev!=device:continue
                            ident=(st.st_dev,st.st_ino)
                            if ident in seen:continue
                            seen.add(ident)
                            result["files"]+=1;result["allocated_bytes"]+=st.st_blocks*512;result["logical_bytes"]+=st.st_size
                        except OSError:continue
            except OSError:continue
    except (OSError,subprocess.SubprocessError):pass
    return result
def measure(storage,contract,*,limit=100000,seconds=4,engine=None,include_engine=True):
    storage=Path(storage);rules=_rules(contract);budgets=contract["log_budgets_mib"]
    categories={};devices={};filesystems={};unknown=[];seen=set()
    journals={name:{"bytes":0,"budget_bytes":n*1024*1024,"partial":False} for name,n in budgets.items()}
    errors=0;partial=False;count=0;wal=0
    flags=os.O_DIRECTORY|os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC
    def fs(path):
        nonlocal errors
        try:
            dev,info=capacity(path);filesystems[dev]=info
        except OSError:errors+=1
    fs(storage/"app")
    def account(key,st):
        nonlocal wal
        category=next((name for _,name,p in rules if p.fullmatch(key)),"unknown")
        service=None
        if key.startswith("logs/"):
            service=key.split("/")[1]
            if service=="caddy":service="/".join(key.split("/")[1:3])
        if category=="service_log" and service not in budgets:category="unknown"
        if not stat.S_ISREG(st.st_mode):category="unknown"
        ident=(st.st_dev,st.st_ino);duplicate=ident in seen;seen.add(ident)
        for row in (categories.setdefault(category,counters()),devices.setdefault(str(st.st_dev),counters())):
            row["files"]+=1;row["logical_bytes"]+=st.st_size;row["allocated_bytes"]+=0 if duplicate else st.st_blocks*512;row["hardlink_paths"]+=int(duplicate)
        if key.startswith("infrastructure/postgres/data/pg_wal/") and not duplicate:wal+=st.st_blocks*512
        if category=="unknown" and len(unknown)<100:unknown.append({"path":key,"reason":"unclassified_or_nonregular_host_path","logical_bytes":st.st_size})
        if service in journals:journals[service]["bytes"]+=st.st_size
    def visit(fd,key,deadline,max_entries,depth=0):
        nonlocal count,errors,partial
        if depth>64:partial=True;return
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    if count>=max_entries or time.monotonic()>deadline:partial=True;return
                    count+=1;rel=key+"/"+entry.name if key else entry.name
                    try:
                        st=entry.stat(follow_symlinks=False)
                        if stat.S_ISDIR(st.st_mode):
                            child=os.open(entry.name,flags,dir_fd=fd)
                            try:
                                if str(st.st_dev) not in filesystems:fs(child)
                                visit(child,rel,deadline,max_entries,depth+1)
                            finally:os.close(child)
                        else:account(rel,st)
                    except FileNotFoundError:continue
                    except OSError:errors+=1
        except OSError:errors+=1
    root=os.open(storage,flags)
    try:
        for key in ("logs","infrastructure","system"):
            try:fd=os.open(key,flags,dir_fd=root)
            except OSError:errors+=1;continue
            try:fs(fd);visit(fd,key,time.monotonic()+seconds/4,count+max(1,limit//4))
            finally:os.close(fd)
        with os.scandir(root) as entries:
            deadline=time.monotonic()+seconds/4;cap=count+max(1,limit//4)
            for entry in entries:
                if entry.name in ("app","logs","infrastructure","system"):continue
                if count>=cap or time.monotonic()>deadline:partial=True;break
                count+=1
                try:
                    st=entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(st.st_mode):
                        fd=os.open(entry.name,flags,dir_fd=root)
                        try:fs(fd);visit(fd,entry.name,deadline,cap)
                        finally:os.close(fd)
                    else:account(entry.name,st)
                except OSError:errors+=1
    finally:os.close(root)
    partial=partial or bool(errors)
    for row in journals.values():row["partial"]=partial
    if engine is None:engine=engine_metrics() if include_engine else {"available":False}
    if engine.get("root"):fs(Path(engine["root"]))
    partial=partial or bool(errors)
    return {"at":datetime.now(timezone.utc).isoformat(),"categories":categories,"devices":devices,"filesystems":filesystems,"unknown_sample":unknown,"partial":partial,"errors":errors,"postgres_wal_subset_bytes":wal,"docker":engine,"deleted_open":deleted_open(storage) if include_engine else None,"tmpfs":runtime_tmpfs() if include_engine else None,"journals":journals,"basis":"bounded_host_protected_inode_sample; app registry separate"}
