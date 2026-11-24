"""Host-only updater. Fixed repository, branch and protocol; no arbitrary commands."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
import re
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from datetime import datetime,timezone
import map_build

ROOT=Path("/var/lib/map-updater")
CONTROL=ROOT/"control"
PRIVATE=ROOT/"private"
STATE=CONTROL/"status.json"
MARKER=CONTROL/"maintenance"
LOCK=CONTROL/"activity.lock"
PROJECT="outdoor-sorter"
SERVICES=("api","worker","cleanup","thumbnail")
ALL=(*SERVICES,"postgres","caddy")
REV=re.compile(r"[0-9a-f]{40}")
REPO_URLS={"https://github.com/chapaayy/Sorter","https://github.com/chapaayy/Sorter.git",
           "git@github.com:chapaayy/Sorter.git","ssh://git@github.com/chapaayy/Sorter.git"}
MIN_FREE=8*1024**3
ROLLBACK="map-local/app:rollback"

def now():
    return datetime.now(timezone.utc).isoformat()

def cmd(args,cwd=None,timeout=120,env=None):
    result=subprocess.run(args,cwd=cwd,timeout=timeout,env=env,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if result.returncode:
        # Output of Docker and install.sh may contain secrets.
        raise RuntimeError("Команда "+args[0]+" завершилась с кодом "+str(result.returncode))
    return result.stdout.strip()

def docker(*args,timeout=120):
    return cmd(["docker",*args],timeout=timeout)

def atomic_json(path,value):
    temp=path.with_name("."+path.name+".tmp")
    with temp.open("w",encoding="utf-8") as out:
        json.dump(value,out,ensure_ascii=False)
        out.flush()
        os.fsync(out.fileno())
    os.chmod(temp,0o644)
    os.replace(temp,path)

def service_id(service):
    ids=docker("ps","-q","--filter","label=com.docker.compose.project="+PROJECT,
               "--filter","label=com.docker.compose.service="+service).splitlines()
    if len(ids)!=1 or not re.fullmatch(r"[0-9a-f]{12,64}",ids[0]):
        raise RuntimeError("Нет единственного работающего контейнера "+service)
    return ids[0]

def inspect_container(service):
    return json.loads(docker("inspect",service_id(service)))[0]

def image_info(image):
    return json.loads(docker("image","inspect",image))[0]

def installed():
    images=[inspect_container(s)["Image"] for s in SERVICES]
    if len(set(images))!=1:
        raise RuntimeError("Контейнеры MAP используют разные образы; требуется install.sh")
    labels=image_info(images[0])["Config"].get("Labels") or {}
    revision=labels.get("org.opencontainers.image.revision","")
    if labels.get("io.map.project")!=PROJECT or not REV.fullmatch(revision):
        raise RuntimeError("Рабочий образ не маркирован обновлятором")
    return revision,images[0]

def sql(statement):
    return docker("exec",service_id("postgres"),"psql","-X","-A","-t",
                  "-v","ON_ERROR_STOP=1","-U","sorter","-d","sorter","-c",statement)

def recent_uploads():
    return int(sql("""SELECT
      (SELECT count(*) FROM uploads WHERE NOT finalized
        AND greatest(created_at,updated_at)>now()-interval '10 minutes') +
      (SELECT count(*) FROM reference_import_files WHERE state='pending'
        AND updated_at>now()-interval '10 minutes')"""))

def verify_idle():
    active=int(sql("""SELECT
       (SELECT count(*) FROM jobs WHERE status IN ('running','stopping')) +
       (SELECT count(*) FROM work_queue WHERE state='running') +
       (SELECT count(*) FROM batch_operations WHERE heartbeat_at>now()-interval '12 hours') +
       (SELECT count(*) FROM thumbnail_tasks WHERE state='running') +
       (SELECT count(*) FROM cleanup_tasks WHERE state='running') +
       (SELECT count(*) FROM archive_retries WHERE state='running')"""))
    if active:
        raise RuntimeError("В БД ещё есть незавершённые операции; переключение отменено")
    if recent_uploads():
        raise RuntimeError("Есть недавние незавершённые загрузки. Завершите их и повторите.")

def disk_available(project):
    paths=[project,ROOT,Path("/var/lib/docker"),Path("/var/lib/containerd")]
    return min(shutil.disk_usage(p).free for p in paths if p.exists())

def backup(project,revision):
    directory=PRIVATE/("backup-"+revision[:12]+"-"+uuid.uuid4().hex)
    directory.mkdir(mode=0o700)
    for name in (".env",".env.generated","compose.yaml"):
        shutil.copy2(project/name,directory/name)
        os.chmod(directory/name,0o600)
    dump=directory/"postgres.dump"
    with dump.open("wb") as stream:
        subprocess.run(["docker","exec",service_id("postgres"),"pg_dump","-Fc",
                        "-U","sorter","-d","sorter"],stdout=stream,stderr=subprocess.PIPE,
                       timeout=1800,check=True)
        stream.flush()
        os.fsync(stream.fileno())
    with dump.open("rb") as stream:
        subprocess.run(["docker","exec","-i",service_id("postgres"),"pg_restore","-l"],
                       stdin=stream,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                       timeout=120,check=True)
    return directory

def clean_images(current,previous):
    warnings=[]
    tags=docker("image","ls","--filter","reference=map-local/app:rev-*",
                "--format","{{.Repository}}:{{.Tag}}").splitlines()
    for tag in tags:
        match=re.fullmatch(r"map-local/app:rev-([0-9a-f]{40})",tag)
        if not match or match[1] in (current,previous):
            continue
        try:
            info=image_info(tag)
            labels=info["Config"].get("Labels") or {}
            if labels.get("io.map.project")!=PROJECT or labels.get("org.opencontainers.image.revision")!=match[1]:
                continue
            if docker("ps","-aq","--filter","ancestor="+info["Id"]):
                continue
            docker("image","rm",tag)  # no force or volume deletion
        except (RuntimeError,OSError,subprocess.SubprocessError):
            warnings.append("Не удалён старый образ "+tag)
    return warnings

class Updater:
    def __init__(self,project):
        self.project=project
        self.mutex=threading.Lock()
        self.exit_requested=False
        try:
            self.state=json.loads(STATE.read_text())
        except (OSError,ValueError):
            self.state={}
        self.state.update(available=True,busy=False)
        if MARKER.exists():
            self.state.update(phase="recovery_required",detail="Прервано переключение версии. Нужна проверка на сервере.")
        elif self.state.get("phase") not in ("success","failed","checked"):
            self.state.update(phase="idle",detail="Готов к проверке обновлений",update_available=False)
        try:
            self.state["installed"]=installed()[0]
        except Exception:
            self.state["installed"]=None
        atomic_json(STATE,self.state)

    def publish(self,**fields):
        with self.mutex:
            self.state.update(fields,updated_at=now())
            atomic_json(STATE,self.state)

    def status(self):
        with self.mutex:
            return dict(self.state)

    def git(self,*args):
        return cmd(["git",*args],cwd=self.project)

    def target(self):
        if self.git("remote","get-url","origin") not in REPO_URLS:
            raise RuntimeError("origin не соответствует репозиторию MAP")
        if self.git("symbolic-ref","--short","HEAD")!="main":
            raise RuntimeError("Рабочая ветка должна быть main")
        if self.git("status","--porcelain","--untracked-files=no"):
            raise RuntimeError("Есть локальные изменения отслеживаемых файлов")
        self.git("fetch","--no-tags","origin","main")
        target=self.git("rev-parse","FETCH_HEAD")
        if not REV.fullmatch(target):
            raise RuntimeError("Некорректная версия Git")
        self.git("merge-base","--is-ancestor","HEAD",target)
        return target

    def check(self):
        try:
            revision,_=installed()
            target=self.target()
            self.publish(phase="checked",installed=revision,target=target,
                         update_available=revision!=target,
                         detail="Доступно обновление" if revision!=target else "Установлена актуальная версия")
        except Exception as exc:
            self.publish(phase="failed",detail=str(exc)[:300],update_available=False)
        finally:
            self.publish(busy=False)

    def dispatch(self,command):
        if command=="status":
            return self.status()
        with self.mutex:
            if self.state.get("busy") or MARKER.exists():
                return {"rejected":True,"detail":"Обновление уже выполняется или требуется восстановление"}
            target=self.state.get("target")
            if command=="update" and (not self.state.get("update_available") or not isinstance(target,str) or not REV.fullmatch(target)):
                return {"rejected":True,"detail":"Сначала проверьте обновления"}
            if command not in ("check","update"):
                return {"rejected":True,"detail":"Неизвестная операция"}
            self.state.update(busy=True,phase="checking" if command=="check" else "preflight",
                              detail="Проверка",updated_at=now())
            atomic_json(STATE,self.state)
            result=dict(self.state)
        threading.Thread(target=self.check if command=="check" else self.update,
                         args=() if command=="check" else (target,),daemon=True).start()
        return result

    def update(self,expected):
        locked=gate=None
        switched=False
        marked=False
        warnings=[]
        try:
            locked=(ROOT/"deploy.lock").open("a")
            fcntl.flock(locked,fcntl.LOCK_EX|fcntl.LOCK_NB)
            old,old_image=installed()
            target=self.target()
            if target!=expected or target==old:
                raise RuntimeError("Версия изменилась; выполните новую проверку")
            if self.git("rev-parse","HEAD")!=old:
                raise RuntimeError("Исходники и работающий образ не совпадают")
            if disk_available(self.project)<MIN_FREE:
                raise RuntimeError("Для сборки требуется не менее 8 ГиБ свободного места")
            if recent_uploads():
                raise RuntimeError("Недавно начата или прервана загрузка. Завершите её перед обновлением.")
            for service in SERVICES:
                info=inspect_container(service)
                if not any(m.get("Source")==str(CONTROL) and m.get("Destination")=="/run/map-updater"
                           and not m.get("RW") for m in info.get("Mounts",[])):
                    raise RuntimeError("Отсутствует защищённый канал обновления: "+service)
                docker("exec",service_id(service),"test","-f","/run/map-updater/activity.lock")
            before=shutil.disk_usage(self.project).free
            self.publish(phase="building",detail="Сборка нового образа; MAP продолжает работать",
                         free_before=before,free_change=None,warnings=[])
            with tempfile.TemporaryDirectory(prefix="source-",dir=PRIVATE) as directory:
                archive=Path(directory)/"source.tar"
                with archive.open("wb") as out:
                    subprocess.run(["git","archive","--format=tar",target],cwd=self.project,
                                   stdout=out,check=True,timeout=120)
                subprocess.run(["tar","-xf",str(archive),"-C",directory],check=True,timeout=120)
                archive.unlink()
                warnings+=map_build.build(Path(directory),target,"map-local/app:rev-"+target)
            self.publish(phase="draining",detail="Ожидание завершения текущих операций",warnings=warnings)
            MARKER.touch(mode=0o644,exist_ok=False)
            marked=True
            gate=LOCK.open("rb")
            deadline=time.monotonic()+7200
            while True:
                try:
                    fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic()>=deadline:
                        raise RuntimeError("Не удалось дождаться завершения операций")
                    time.sleep(1)
            verify_idle()
            self.publish(phase="backup",detail="Резервная копия базы и конфигурации")
            backup_dir=backup(self.project,old)
            docker("tag",old_image,ROLLBACK)
            docker("tag",old_image,"map-local/app:rev-"+old)
            self.publish(previous=old,backup=backup_dir.name)
            switched=True
            self.publish(phase="deploying",detail="Переключение контейнеров")
            docker("tag","map-local/app:rev-"+target,map_build.CURRENT)
            self.git("merge","--ff-only",target)
            env=dict(os.environ,MAP_UPDATER_PREBUILT="1")
            cmd(["bash","install.sh","--deploy"],cwd=self.project,timeout=1800,env=env)
            self.publish(phase="health",detail="Проверка новой версии")
            deadline=time.monotonic()+180
            while True:
                try:
                    if installed()[0]!=target:
                        raise RuntimeError("Не все контейнеры обновлены")
                    for service in ALL:
                        state=inspect_container(service)["State"]
                        if not state["Running"] or state.get("Health",{}).get("Status","healthy")!="healthy":
                            raise RuntimeError("Контейнер не готов: "+service)
                    if int(sql("""SELECT count(*) FROM service_heartbeats
                          WHERE service IN ('megaloc','thumbnail','cleanup')
                            AND seen_at>now()-interval '35 seconds'"""))!=3:
                        raise RuntimeError("Нет heartbeat всех работников")
                    break
                except (RuntimeError,OSError,subprocess.SubprocessError):
                    if time.monotonic()>=deadline:
                        raise
                    time.sleep(3)
            self.publish(phase="cleanup",detail="Очистка только собственных старых сборок")
            try:
                warnings+=clean_images(target,old)
                warnings+=map_build.clean_owned_builders()
                for path in PRIVATE.glob("backup-*"):
                    if path!=backup_dir and path.is_dir() and not path.is_symlink() and re.fullmatch(r"backup-[0-9a-f]{12}-[0-9a-f]{32}",path.name):
                        shutil.rmtree(path)
            except Exception:
                warnings.append("Часть старых служебных данных обновлятора не удалена")
            after=shutil.disk_usage(self.project).free
            MARKER.unlink()
            self.publish(phase="success",installed=target,target=target,update_available=False,
                         detail="MAP обновлён",warnings=warnings,free_after=after,
                         free_change=after-before,busy=False)
            self.exit_requested=True
        except Exception as exc:
            if not switched and marked:
                MARKER.unlink(missing_ok=True)
            self.publish(phase="recovery_required" if switched else "failed",
                         detail=str(exc)[:350],busy=False,warnings=warnings,
                         update_available=not switched)
        finally:
            if gate is not None:
                gate.close()
            if locked is not None:
                locked.close()

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        _,uid,_=struct.unpack("3i",self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid not in (0,10001):
            return
        try:
            line=self.rfile.readline(32)
            if line not in (b"status\n",b"check\n",b"update\n"):
                return
            result=self.server.updater.dispatch(line.decode().strip())
            self.wfile.write((json.dumps(result,ensure_ascii=False)+"\n").encode())
        except (OSError,ValueError):
            return

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--project-root",type=Path,required=True)
    args=parser.parse_args()
    if os.geteuid()!=0:
        parser.error("root required")
    os.umask(0o077)
    project=args.project_root.resolve(strict=True)
    if project.stat().st_uid!=0 or project.stat().st_mode&0o022:
        parser.error("project must be root-owned and not group/world writable")
    socket_path=CONTROL/"control.sock"
    socket_path.unlink(missing_ok=True)
    updater=Updater(project)
    with socketserver.UnixStreamServer(str(socket_path),Handler) as server:
        server.updater=updater
        os.chown(socket_path,0,10001)
        os.chmod(socket_path,0o660)
        server.timeout=1
        while not updater.exit_requested:
            server.handle_request()
    socket_path.unlink(missing_ok=True)

if __name__=="__main__":
    main()
