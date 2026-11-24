"""Real CI-only root host updater harness with two local commits, no production remote writes."""
import hashlib
import json
import os
import shutil
import ssl
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
import map_updater as host
import map_build
from host_logs import prune_postgres

BRANCH="feature/storage-architecture-v2"
def run(*args,cwd=None,env=None,timeout=120):
    return subprocess.check_output(args,cwd=cwd,env=env,timeout=timeout,text=True).strip()
def compose(root,*args,timeout=180):
    return run("docker","compose","--env-file",".env","--env-file",".env.generated",*args,cwd=root,timeout=timeout)

def tls():
    with socket.create_connection(("127.0.0.1",443),timeout=5) as raw:
        with ssl._create_unverified_context().wrap_socket(raw,server_hostname="localhost") as conn:
            return hashlib.sha256(conn.getpeercert(binary_form=True)).hexdigest()

def permanent(storage):
    roots=[storage/"app"/x for x in ("users","shared/references","models/megaloc")]
    result={}
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                st=path.stat()
                with path.open("rb") as stream:digest=hashlib.file_digest(stream,"sha256").hexdigest()
                result[str(path.relative_to(storage))]=(st.st_ino,st.st_size,st.st_mtime_ns,digest)
    assert any("/embeddings/" in p for p in result) and any("/weights/" in p for p in result)
    return result

def await_health():
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        try:
            host.check_proxy()
            if len(host.worker_instances())==3:return
        except Exception:pass
        time.sleep(2)
    raise RuntimeError("CI health deadline exceeded")

def check_logs(root,storage):
    # Actual Caddy logs use small test-only roll thresholds. Send confidential
    # synthetic values in headers and query; none may reach the files.
    secret="CI_LOG_SECRET_7b3f1a"
    for _ in range(35):
        run("curl","-kfsS","--max-time","5","-o","/dev/null","-H","Authorization: Bearer "+secret,
            "-H","Cookie: ci="+secret,"https://localhost/api/health?token="+secret)
    for kind,basename in (("access","access"),("runtime","caddy")):
        path=storage/"logs/caddy"/kind
        assert (path/(basename+".jsonl")).is_file(),path
        if kind=="runtime":
            for _ in range(5):
                compose(root,"exec","-T","caddy","caddy","reload","--config","/etc/caddy/Caddyfile","--force")
        rotated=[p for p in path.iterdir() if p.name!=basename+".jsonl"]
        assert rotated,(kind,list(path.iterdir()))
        assert len(rotated)<=4
        import gzip
        for p in path.iterdir():
            data=gzip.open(p,"rb").read() if p.suffix==".gz" else p.read_bytes()
            assert secret.encode() not in data
    # PostgreSQL collector writes native logs and real pg_rotate_logfile closes
    # each old segment. The actual host retention helper preserves active file.
    for i in range(3):
        host.sql("DO $$ BEGIN RAISE WARNING 'CI rotation marker'; END $$")
        time.sleep(1.1)
        host.sql("SELECT pg_rotate_logfile()")
        time.sleep(1.1)
    active=(storage/"infrastructure/postgres/data/current_logfiles").read_text().split()[1]
    active_file=storage/"logs/postgres"/Path(active).name
    assert active_file.exists()
    assert prune_postgres(storage,budget=1)>=1
    assert active_file.exists()
    print("REAL_CADDY_POSTGRES_ROTATION_AND_REDACTION_OK",flush=True)

def main():
    if os.environ.get("CI")!="true" or os.environ.get("GITHUB_ACTIONS")!="true" or os.geteuid()!=0:
        raise RuntimeError("Disposable root CI only")
    root=Path(sys.argv[1]).resolve()
    storage=Path(sys.argv[2]).resolve()
    assert storage==root/"storage" and (root/".env.generated").exists()
    old=run("git","rev-parse","HEAD",cwd=root)
    assert host.installed()[0]==old
    compose(root,"up","-d","--no-build","--wait","--wait-timeout","180")
    await_health()
    initial=permanent(storage)
    credentials=(root/".env.generated").read_bytes()
    cert=tls()
    pgid=host.sql("SELECT system_identifier FROM pg_control_system()")
    pg_before=host.service_id("postgres")
    caddy_before=host.service_id("caddy")
    # Real repeat deployment (same prebuilt verified revision, no re-download).
    env=dict(os.environ,MAP_UPDATER_PREBUILT="1")
    run("bash","install.sh","--deploy",cwd=root,env=env,timeout=300)
    assert (root/".env.generated").read_bytes()==credentials
    compose(root,"up","-d","--no-build","--force-recreate","--wait","--wait-timeout","180","postgres","caddy")
    await_health()
    assert pg_before!=host.service_id("postgres") and caddy_before!=host.service_id("caddy")
    assert host.sql("SELECT system_identifier FROM pg_control_system()")==pgid and tls()==cert
    assert permanent(storage)==initial
    assert (storage/"infrastructure/postgres/data").stat().st_uid==70
    assert (storage/"system/updater/control/activity.lock").stat().st_mode&0o777==0o644
    assert (storage/"infrastructure/caddy/data").stat().st_uid==0
    assert not run("docker","volume","ls","-q","--filter","label=com.docker.compose.project=outdoor-sorter")
    print("REAL_REPEAT_INSTALL_AND_RECREATE_PERSISTENCE_OK",flush=True)
    check_logs(root,storage)
    with tempfile.TemporaryDirectory(prefix="map-ci-update-") as folder:
        temp=Path(folder);project=temp/"project";remote=temp/"origin.git"
        # Git data stays strictly local to this disposable CI host. The
        # production URL and branch pin remain the same; Git's local transport
        # rewrite is root-controlled and never supplied through the API.
        run("git","clone","--no-hardlinks","--no-checkout",str(root),str(project))
        run("git","checkout","-B",BRANCH,old,cwd=project)
        run("git","init","--bare",str(remote))
        run("git","push",str(remote),BRANCH,cwd=project)
        run("git","config","user.name","CI storage acceptance",cwd=project)
        run("git","config","user.email","ci@example.invalid",cwd=project)
        marker=project/"docs/ci-stage6-update-marker.txt"
        marker.write_text("Disposable update fixture\n")
        run("git","add","docs/ci-stage6-update-marker.txt",cwd=project)
        run("git","commit","-m","CI-only next revision",cwd=project)
        target=run("git","rev-parse","HEAD",cwd=project)
        run("git","push",str(remote),BRANCH,cwd=project)
        run("git","reset","--hard",old,cwd=project)
        run("git","remote","set-url","origin","https://github.com/chapaayy/Sorter.git",cwd=project)
        run("git","config","url.file://"+str(remote)+".insteadOf","https://github.com/chapaayy/Sorter.git",cwd=project)
        # Do not let checkout config alter the tracked branch or credentials.
        for name in (".env",".env.generated"):
            shutil.copy2(root/name,project/name)
        host.configure(storage,project)
        # Run the actual root Unix-socket daemon and send its fixed RPC commands.
        daemon=subprocess.Popen([sys.executable,str(Path(__file__).with_name("map_updater.py")),
                     "--project-root",str(project),"--storage-root",str(storage)])
        def rpc(command):
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect(str(host.RPC/"control.sock"))
                sock.sendall((command+"\n").encode())
                with sock.makefile("rb") as stream:return json.loads(stream.readline(65536))
        def wait_phase(expected,timeout=300):
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                try:state=json.loads(host.STATE.read_text())
                except (OSError,ValueError):
                    time.sleep(.3);continue
                if state.get("phase")==expected and not state.get("busy"):return state
                if state.get("phase") in ("failed","recovery_required") and not state.get("busy"):
                    raise RuntimeError("Updater failure: "+str(state.get("detail")))
                time.sleep(.5)
            raise RuntimeError("Updater acceptance deadline: "+expected)
        try:
            deadline=time.monotonic()+10
            while not (host.RPC/"control.sock").exists() and time.monotonic()<deadline:time.sleep(.1)
            assert rpc("status")["branch"]==BRANCH
            rpc("check")
            state=wait_phase("checked")
            assert state["target"]==target and state["update_available"],state
            rpc("update")
            wait_phase("success",1200)
            assert daemon.wait(timeout=10)==0
        finally:
            if daemon.poll() is None:
                daemon.terminate()
                daemon.wait(timeout=20)
        assert host.installed()[0]==target
        assert run("git","rev-parse","HEAD",cwd=project)==target
        assert host.sql("SELECT system_identifier FROM pg_control_system()")==pgid and tls()==cert
        assert (project/".env.generated").read_bytes()==credentials and permanent(storage)==initial
        assert not list(host.WORKSPACE.iterdir()) and not list(map_build.STATE.iterdir())
        backups=list(host.BACKUPS.glob("backup-*"))
        assert len(backups)==1 and (backups[0]/"postgres.dump").stat().st_size>0
        assert host.image_info("map-local/app:rev-"+old) and host.image_info("map-local/app:rev-"+target)
        assert not host.MARKER.exists()
        assert (storage/"logs/updater/service.jsonl").stat().st_size>0
        print("REAL_TWO_COMMIT_UPDATER_PRESERVATION_OK",old,target,flush=True)
        # Project bind paths for Caddy must outlive this fixture checkout.
        compose(root,"up","-d","--no-build","--force-recreate","--wait","--wait-timeout","180","caddy")
    print("STAGE6_REAL_HOST_HARNESS_OK",flush=True)

if __name__=="__main__":main()
