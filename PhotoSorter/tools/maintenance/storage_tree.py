"""Independent, bounded, read-only st_blocks census of the storage tree.

No quota mutations, no traversal of symlinks, no read of file contents.
A live walk is not an atomic filesystem snapshot.
"""
from datetime import datetime,timezone
import os
import re
import stat
import subprocess
import json
import time

def utcnow():return datetime.now(timezone.utc).isoformat()

def _bucket():
    return {"file_bytes":0,"directory_bytes":0,"files":0,"directories":0,"hardlink_paths":0}

def measure_tree(storage,*,limit=250000,seconds=20):
    report={"started_at":utcnow(),"finished_at":None,"app":_bucket(),"host":_bucket(),
            "errors":0,"changed_directories":0,"other_devices":0,"cross_scope_links":0,
            "limit_reached":False,"entries":0,"partial":True}
    seen={};deadline=time.monotonic()+seconds
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
    def allowed():
        if report["entries"]>=limit or time.monotonic()>=deadline:
            report["limit_reached"]=True
            return False
        return True
    def account(st,scope):
        report["entries"]+=1
        row=report[scope];isdir=stat.S_ISDIR(st.st_mode)
        row["directories" if isdir else "files"]+=1
        # Directories and multiply linked nodes require device+inode dedup.
        if isdir or st.st_nlink>1:
            ident=(st.st_dev,st.st_ino)
            if ident in seen:
                row["hardlink_paths"]+=1
                if scope!=seen[ident]:report["cross_scope_links"]+=1
                return False
            seen[ident]=scope
        row["directory_bytes" if isdir else "file_bytes"]+=st.st_blocks*512
        return True
    def visit(fd,scope,depth=0):
        if not allowed():return
        if depth>64:
            report["errors"]+=1
            return
        before=os.fstat(fd)
        if not account(before,scope):return
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    if not allowed():break
                    try:
                        st=entry.stat(follow_symlinks=False)
                        child_scope="app" if depth==0 and entry.name=="app" else scope
                        if st.st_dev!=device:
                            report["other_devices"]+=1
                            continue
                        if stat.S_ISDIR(st.st_mode):
                            child=os.open(entry.name,flags,dir_fd=fd)
                            try:
                                actual=os.fstat(child)
                                if (actual.st_dev,actual.st_ino)!=(st.st_dev,st.st_ino):
                                    report["errors"]+=1
                                    continue
                                visit(child,child_scope,depth+1)
                            finally:os.close(child)
                        else:account(st,child_scope)
                    except OSError:report["errors"]+=1
        except OSError:report["errors"]+=1
        after=os.fstat(fd)
        if (before.st_mtime_ns,before.st_ctime_ns,before.st_blocks)!=(after.st_mtime_ns,after.st_ctime_ns,after.st_blocks):
            report["changed_directories"]+=1
    try:
        fd=os.open(storage,flags)
        try:
            device=os.fstat(fd).st_dev
            report["device"]=str(device)
            visit(fd,"host")
        finally:os.close(fd)
    except OSError:report["errors"]+=1
    report["directory_bytes"]=sum(report[k]["directory_bytes"] for k in ("app","host"))
    report["allocated_bytes"]=sum(report[k]["file_bytes"]+report[k]["directory_bytes"] for k in ("app","host"))
    report["partial"]=bool(report["errors"] or report["limit_reached"] or report["changed_directories"] or report["other_devices"] or report["cross_scope_links"])
    report["finished_at"]=utcnow()
    return report

def registry_sample():
    # Fixed local Compose project/service, no user-supplied shell or paths.
    try:
        ids=subprocess.check_output(["docker","ps","-q","--filter","label=com.docker.compose.project=outdoor-sorter",
             "--filter","label=com.docker.compose.service=api"],text=True,timeout=8).split()
        if len(ids)!=1 or not re.fullmatch(r"[a-f0-9]{12,64}",ids[0]):return None
        command="import json;from server.storage.accounting import snapshot;print(json.dumps(snapshot()))"
        result=json.loads(subprocess.check_output(["docker","exec",ids[0],"python","-c",command],text=True,timeout=8))
        return {k:result.get(k) for k in ("sampled_at","allocated_bytes","partial","pending_changes","reserved_bytes","issues","missing_expected")}
    except (OSError,ValueError,TypeError,subprocess.SubprocessError):return None

def compare(storage,host,*,sample=registry_sample,scan=measure_tree):
    before=sample()
    tree=scan(storage)
    after=sample()
    app=after.get("allocated_bytes") if after else None
    protected=host.get("devices",{}).get(tree.get("device"),{}).get("allocated_bytes")
    tree["registry_before"]=before
    tree["registry_after"]=after
    tree["host_sampled_at"]=host.get("at")
    tree["registry_file_bytes"]=app
    tree["host_file_bytes"]=protected
    tree["app_delta_bytes"]=tree["app"]["file_bytes"]-app if isinstance(app,int) else None
    tree["host_delta_bytes"]=tree["host"]["file_bytes"]-protected if isinstance(protected,int) else None
    stable=bool(before and after and not before.get("partial",True) and not after.get("partial",True)
                and isinstance(app,int) and before.get("allocated_bytes")==app
                and not before.get("pending_changes") and not after.get("pending_changes")
                and not before.get("reserved_bytes") and not after.get("reserved_bytes"))
    # Even stable snapshots are observational, not a filesystem-wide atomic snapshot.
    comparable=stable and not tree["partial"] and not host.get("partial",True) and isinstance(protected,int)
    tree["comparable"]=bool(comparable)
    tree["unexplained_bytes"]=tree["allocated_bytes"]-app-protected-tree["directory_bytes"] if comparable else None
    tree["basis"]="independent_st_blocks_tree_walk_plus_measured_directory_blocks; non_atomic"
    return tree
