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

if __name__=="__main__":
    import sys
    prune_postgres(Path(sys.argv[1]))
