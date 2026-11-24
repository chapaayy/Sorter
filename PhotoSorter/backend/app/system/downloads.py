"""Explicit official MegaLoc installer. A verified marker publishes the bundle."""
from __future__ import annotations
import fcntl
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from app import config
from app.storage.categories import Category
from app.storage.paths import managed_prefix
from app.storage.filesystem import directory_fd,atomic_publish,safe_remove_tree
from app.storage.temporary import download_operation
from app.storage.changes import changed
from . import model_store

def _fetch(url,target,*,maximum,progress=lambda n:None):
    request=urllib.request.Request(url,headers={"User-Agent":"PhotoSorter/5.0"})
    with urllib.request.urlopen(request,timeout=60) as response,target.open("xb") as stream:
        received=0
        while chunk:=response.read(1024*1024):
            received+=len(chunk)
            if received>maximum:raise ValueError("MegaLoc download exceeds expected size")
            stream.write(chunk)
            progress(received)
        stream.flush()
        os.fsync(stream.fileno())

def _publish(stage_source,stage_weight,*,already_reserved=False):
    root=config.APP_STORAGE_ROOT
    source=model_store.repo_folder()
    weight=model_store.weight_target()
    # If a previous good publication exists, never replace it.
    if model_store.verified():return
    # Invalid committed bundles require explicit repair, not destructive retry.
    if model_store.verification_path().exists():
        raise RuntimeError("Committed model is damaged; automatic overwrite refused")
    # Retry after a crash between file publication and marker commit.
    if source.exists():
        try:model_store.verify_source(source)
        except (OSError,ValueError):
            safe_remove_tree(root,source.relative_to(root))
    if not source.exists():
        with directory_fd(root,source.parent.relative_to(root),create=True) as fd:
            os.rename(stage_source,source.name,dst_dir_fd=fd)
            os.fsync(fd)
        changed(stage_source,source,subtree=True)
    if weight.exists():
        if model_store.content_digest(weight)!=model_store.WEIGHT_SHA256:
            raise ValueError("Unexpected existing weight; automatic overwrite refused")
    else:
        atomic_publish(root,stage_weight.relative_to(root),weight.relative_to(root))
    model_store.remember_verified(already_reserved=already_reserved)

class Downloads:
    def __init__(self):
        self.lock=threading.RLock()
        self.states={}
        self.active=False
    def status(self):
        with self.lock:return {k:dict(v) for k,v in self.states.items()}
    def _set(self,status,message,**progress):
        from app.logging.service import log,redact
        message=redact(message)
        if status!='downloading' or progress.get('stage')!='weights':
            try:log('models',status+': '+message)
            except (OSError,ValueError):pass
        with self.lock:self.states["megaloc"]={"status":status,"message":str(message)[-1200:],**progress}
    def start(self,name):
        if name!="megaloc":raise ValueError("Доступна только MegaLoc")
        with self.lock:
            if self.active:raise RuntimeError("Загрузка MegaLoc уже выполняется")
            if model_store.verified():
                self._set("installed","MegaLoc уже проверена")
                return dict(self.states["megaloc"])
            self.active=True
            self._set("downloading","Подготовка загрузки…",stage="prepare")
            threading.Thread(target=self._run,daemon=True,name="megaloc-download").start()
            return dict(self.states["megaloc"])

    def _run(self):
        try:
            from server.services.update_gate import activity
            with activity() as allowed:
                if not allowed:raise RuntimeError("MAP обновляется")
                self.install()
            self._set("installed","MegaLoc загружена и проверена",stage="done")
        except Exception as exc:
            self._set("error",f"{type(exc).__name__}: {exc}",stage="error")
        finally:
            with self.lock:self.active=False

    def install(self):
        from server.services.archive_cache import build_space
        from app.storage.config import StorageConfig
        StorageConfig(config.APP_STORAGE_ROOT).ensure_dirs()
        root=config.APP_STORAGE_ROOT
        meta=managed_prefix(Category.MODEL_METADATA)
        # Stable directory lock covers cross-process installers and marker publication.
        with directory_fd(root,meta.relative_to(root),create=True) as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise RuntimeError("Загрузка MegaLoc уже выполняется")
            if model_store.verified():return
            if model_store.verification_path().exists():raise RuntimeError("Committed model is damaged; automatic overwrite refused")
            with download_operation(root) as (stage,lease):
                source=stage/"source"
                source.mkdir()
                weight=stage/model_store.WEIGHT_NAME
                with build_space(root,model_store.MAX_WEIGHT_BYTES+10_000_000,message="Недостаточно места для установки MegaLoc",kind="model_download",work=stage,tree=True) as budget:
                    budget.publish(model_store.verification_path(),model_store.weight_target(),*(model_store.repo_folder()/name for name in model_store.SOURCE_BLOBS))
                    for name in model_store.SOURCE_BLOBS:
                        _fetch(f"https://raw.githubusercontent.com/gmberton/MegaLoc/{model_store.SOURCE_REVISION}/{name}",
                               source/name,maximum=1_000_000)
                    model_store.verify_source(source)
                    _fetch(f"https://huggingface.co/{model_store.REPO}/resolve/{model_store.WEIGHT_REVISION}/{model_store.WEIGHT_NAME}?download=true",
                           weight,maximum=model_store.MAX_WEIGHT_BYTES,
                           progress=lambda n:self._set("downloading",f"Веса MegaLoc: {n/1024/1024:.1f} МБ",stage="weights",received_bytes=n))
                    model_store.verify_bundle(source,weight)
                    self._set("verifying","Проверяем реальные веса MegaLoc на CPU…",stage="verify")
                    self._verify(source,weight,stage,lease)
                    _publish(source,weight,already_reserved=True)
                    if not model_store.verified():raise RuntimeError("Publication verification failed")

    def _verify(self,source,weight,stage,lease):
        # No automatic Torch Hub download or external dependency is allowed.
        code=("import sys,os,resource,ctypes,signal;"
              "assert ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGKILL,0,0,0)==0;"
              "os.getppid()==int(sys.argv[3]) or os._exit(125);"
              "resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,resource.getrlimit(resource.RLIMIT_FSIZE)[1]));"
              "import torch;from pathlib import Path;"
              "from app.recognition.engines.megaloc.loader import load_megaloc;"
              "torch.set_num_threads(2);"
              "m=load_megaloc(staged=(Path(sys.argv[1]),Path(sys.argv[2])));"
              "torch.set_grad_enabled(False);x=m(torch.zeros(1,3,322,322));"
              "assert tuple(x.shape)==(1,8448) and torch.isfinite(x).all();print('MODEL_OK')")
        env=os.environ.copy()
        env.update({k:str(stage) for k in ("TMPDIR","TEMP","TMP")})
        log=stage/"verify.log"
        with log.open("wb") as output:
            result=subprocess.run([sys.executable,"-c",code,str(source),str(weight),str(os.getpid())],stdout=output,
                                  stderr=subprocess.STDOUT,env=env,pass_fds=(lease,),timeout=420)
        if result.returncode or b"MODEL_OK" not in log.read_bytes():
            raise RuntimeError("MegaLoc verification failed: "+log.read_bytes()[-1400:].decode(errors="replace"))

downloads=Downloads()
