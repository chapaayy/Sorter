"""Disposable MAP-only BuildKit; never prune a shared/default builder."""
import argparse
import re
import json
import signal
import subprocess
import uuid
from pathlib import Path

STATE=None

def configure(storage):
    global STATE
    STATE=Path(storage)/"system/updater/private/builders"
CURRENT="map-local/app:current"
PROJECT="outdoor-sorter"

def run(args, cwd=None, timeout=7200):
    subprocess.run(args,cwd=cwd,timeout=timeout,check=True)

def clean_owned_builders():
    if STATE is None:raise RuntimeError("Builder storage root not configured")
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    warnings=[]
    for marker in STATE.iterdir():
        if not re.fullmatch(r"map-sorter-[0-9a-f]{32}",marker.name) or not marker.is_file():
            continue
        try:
            run(["docker","buildx","rm",marker.name],timeout=120)
            marker.unlink()
        except (OSError,subprocess.SubprocessError):
            # Registry may already be gone after an interrupted removal. Never
            # drop the marker while a matching container or state volume exists.
            try:
                names=subprocess.check_output(["docker","buildx","ls","--format","{{.Name}}"],text=True,timeout=30).splitlines()
                resource="buildx_buildkit_"+marker.name+"0"
                containers=subprocess.check_output(["docker","ps","-a","--format","{{.Names}}"],text=True,timeout=30).splitlines()
                volumes=subprocess.check_output(["docker","volume","ls","--format","{{.Name}}"],text=True,timeout=30).splitlines()
                if marker.name not in names and resource not in containers and resource+"_state" not in volumes:
                    marker.unlink();continue
            except (OSError,subprocess.SubprocessError):pass
            warnings.append("Не удалось удалить builder "+marker.name)
    return warnings

def build(root,revision,tag):
    if not re.fullmatch(r"[0-9a-f]{40}",revision) or tag not in (CURRENT,"map-local/app:rev-"+revision):
        raise ValueError("Invalid MAP image reference")
    warnings=clean_owned_builders()
    name="map-sorter-"+uuid.uuid4().hex
    marker=STATE/name
    marker.touch(mode=0o600,exist_ok=False)
    try:
        run(["docker","buildx","create","--name",name,"--driver","docker-container"],timeout=120)
        run(["docker","buildx","build","--builder",name,"--load",
             "--label","io.map.project="+PROJECT,
             "--label","org.opencontainers.image.revision="+revision,
             "--tag",tag,"--file","PhotoSorter/docker/app/Dockerfile","."],cwd=root)
    finally:
        try:
            run(["docker","buildx","rm",name],timeout=120)
            marker.unlink()
        except (OSError,subprocess.SubprocessError):
            warnings.append("Не удалось удалить builder "+name)
    return warnings

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("revision")
    p.add_argument("--storage-root",type=Path,required=True)
    a=p.parse_args()
    configure(a.storage_root)
    def stop(sig,frame):raise SystemExit(128+sig)
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    for w in build(a.root,a.revision,CURRENT):
        print("[WARN]",w)
    run(["docker","tag",CURRENT,"map-local/app:rev-"+a.revision],timeout=60)
