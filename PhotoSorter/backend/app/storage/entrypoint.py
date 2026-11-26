"""Container PID1 supervisor: private TMPDIR for Python and native children."""
import os
import signal
import subprocess
import sys
from app.logging.service import log
from .temporary import leased_operation
from .categories import Category
from app.system.technical_cache import runtime_guard
import uuid
from app.config import APP_STORAGE_ROOT,ensure_dirs

def main():
    ensure_dirs()
    service=os.environ.get("MAP_SERVICE","api")
    with runtime_guard() as cache_lock, leased_operation(APP_STORAGE_ROOT,Category.SCRATCH,service=service,operation_id=uuid.uuid4()) as (scratch,fd):
        env=os.environ.copy()
        env.update({k:str(scratch) for k in ("TMPDIR","TEMP","TMP")})
        command=sys.argv[1:]
        capture=(command[0]=="uvicorn" or (command[:2]==["python","-m"] and command[2] in ("server.worker","server.workers.cleanup","server.workers.thumbnail")))
        child=subprocess.Popen(command,env=env,pass_fds=(fd,cache_lock),stdout=subprocess.PIPE if capture else None,stderr=subprocess.STDOUT if capture else None)
        def forward(sig,_):
            if child.poll() is None:child.send_signal(sig)
        for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,forward)
        try:
            if capture:
                while line:=child.stdout.readline(8192):
                    try:
                        if not log(service,line.decode("utf8",errors="replace").rstrip()):
                            print("MAP file logging unavailable",file=sys.stderr)
                    except (OSError,ValueError):print("MAP file logging failed",file=sys.stderr)
            return child.wait()
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

if __name__=="__main__":sys.exit(main())
