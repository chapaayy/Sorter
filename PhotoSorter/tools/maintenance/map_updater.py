"""Host-only updater. Fixed repository, branch and protocol; no arbitrary commands."""
from __future__ import annotations
import argparse
import fcntl
import json
import http.client
import ssl
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

ROOT=Path("/nonexistent/map-updater")
CONTROL=ROOT/"control"
RPC=ROOT/"rpc"
PRIVATE=ROOT/"private"
WORKSPACE=ROOT/"workspace"
BACKUPS=ROOT/"backups"
STORAGE=None
BRANCH="feature/storage-architecture-v2"
LOG_DIRECTORY=None
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

def configure(storage,project):
    global ROOT,CONTROL,RPC,PRIVATE,WORKSPACE,BACKUPS,STATE,MARKER,LOCK,STORAGE,BRANCH,LOG_DIRECTORY
    storage=Path(storage)
    if not storage.is_absolute() or storage.resolve()!=storage:raise ValueError("Unsafe storage root")
    pin=storage/"system/state/update-branch"
    info=pin.stat(follow_symlinks=False)
    if pin.is_symlink() or info.st_uid!=0 or info.st_mode&0o077:raise ValueError("Unsafe update branch pin")
    branch=pin.read_text().strip()
    if branch != "feature/storage-architecture-v2":raise ValueError("Invalid trusted branch")
    expected=[line.split("=",1)[1] for line in (project/".env.generated").read_text().splitlines() if line.startswith("MAP_STORAGE_ROOT=")]
    if expected!=[str(storage)]:raise ValueError("Storage pin mismatch")
    STORAGE=storage
    ROOT=storage/"system/updater"
    CONTROL=ROOT/"control";RPC=ROOT/"rpc";PRIVATE=ROOT/"private";WORKSPACE=ROOT/"workspace"
    BACKUPS=storage/"system/backups/updater";LOG_DIRECTORY=storage/"logs/updater"
    STATE=CONTROL/"status.json";MARKER=CONTROL/"maintenance";LOCK=CONTROL/"activity.lock"
    BRANCH=branch
    map_build.configure(storage)

def recover_owned_work(storage=None):
    # Caller owns deployment lock; never remove another running build.
    workspace,backups=WORKSPACE,BACKUPS
    if storage is not None:
        storage=Path(storage)
        map_build.configure(storage)
        workspace=storage/"system/updater/workspace"
        backups=storage/"system/backups/updater"
    warnings=map_build.clean_owned_builders()
    for path in workspace.glob("source-*"):
        if path.is_dir() and not path.is_symlink():shutil.rmtree(path)
    for path in backups.glob(".pending-*"):
        if path.is_dir() and not path.is_symlink():shutil.rmtree(path)
    return warnings

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
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

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
       (SELECT count(*) FROM cleanup_tasks WHERE state='running')"""))
    if active:
        raise RuntimeError("В БД ещё есть незавершённые операции; переключение отменено")
    if recent_uploads():
        raise RuntimeError("Есть недавние незавершённые загрузки. Завершите их и повторите.")

def worker_instances():
    return set(sql("""SELECT instance_id::text FROM service_heartbeats
                       WHERE service IN ('megaloc','thumbnail','cleanup')""").splitlines())

def check_proxy():
    env=inspect_container("caddy")["Config"].get("Env",[])
    domains=[x.split("=",1)[1] for x in env if x.startswith("DOMAIN=")]
    if len(domains)!=1 or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9.-]*",domains[0]):
        raise RuntimeError("Некорректный домен Caddy")
    # Probe only localhost's real HTTPS proxy, with its actual SNI/Host.
    # Certificate validation belongs to external clients; this is local health.
    domain=domains[0]
    with socket.create_connection(("127.0.0.1",443),timeout=8) as raw:
        with ssl._create_unverified_context().wrap_socket(raw,server_hostname=domain) as tls:
            tls.sendall(("GET /api/health HTTP/1.1\r\nHost: "+domain+
                         "\r\nConnection: close\r\n\r\n").encode("ascii"))
            response=http.client.HTTPResponse(tls)
            response.begin()
            if response.status!=200 or json.loads(response.read(65536)).get("status")!="ok":
                raise RuntimeError("Caddy не возвращает здоровый API")

def disk_available(project):
    paths=[project,STORAGE or ROOT,Path("/var/lib/docker"),Path("/var/lib/containerd")]
    return min(shutil.disk_usage(p).free for p in paths if p.exists())

def backup(project,revision):
    name="backup-"+revision[:12]+"-"+uuid.uuid4().hex
    directory=BACKUPS/(".pending-"+name)
    directory.mkdir(mode=0o700)
    for filename in (".env",".env.generated","compose.yaml"):
        shutil.copy2(project/filename,directory/filename)
        os.chmod(directory/filename,0o600)
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
    (directory/"revision").write_text(revision+"\n")
    for file in directory.iterdir():
        with file.open("rb") as stream:os.fsync(stream.fileno())
    published=BACKUPS/name
    os.rename(directory,published)
    fd=os.open(BACKUPS,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return published

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
        self.state.update(available=True,busy=False,branch=BRANCH,storage_maintenance_supported=True)
        action=self.state.get("storage_action")
        if isinstance(action,dict) and action.get("state")=="running":
            self.state["storage_action"]={**action,"state":"interrupted","finished_at":now(),
                "detail":"Хостовая операция прервана; проверьте состояние сервисов."}
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
            if LOG_DIRECTORY is not None and "phase" in fields:
                # Host log contains only trusted phase/revision, not command output.
                from host_logs import record
                try:record(LOG_DIRECTORY,"updater",str(fields["phase"]))
                except OSError:pass
            atomic_json(STATE,self.state)

    def status(self):
        with self.mutex:
            return dict(self.state)

    def git(self,*args):
        return cmd(["git",*args],cwd=self.project)

    def target(self):
        if self.git("config","--get","remote.origin.url") not in REPO_URLS:
            raise RuntimeError("origin не соответствует репозиторию MAP")
        if self.git("symbolic-ref","--short","HEAD")!=BRANCH:
            raise RuntimeError("Рабочая ветка не соответствует закреплённой ветке установки")
        if self.git("status","--porcelain","--untracked-files=no"):
            raise RuntimeError("Есть локальные изменения отслеживаемых файлов")
        self.git("fetch","--no-tags","origin",BRANCH)
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
            if command in ("storage-cache","storage-logs"):
                self.state.update(busy=True,storage_action={"kind":command,"state":"running","started_at":now()},
                                  updated_at=now())
                atomic_json(STATE,self.state)
                result=dict(self.state)
                threading.Thread(target=self.storage_maintenance,args=(command,),daemon=True).start()
                return result
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

    def storage_maintenance(self,command):
        """Restricted host action, mutually exclusive with deploy/installer.
        No user paths, shell text, foreign images, or online cache deletion.
        """
        if command not in ("storage-cache","storage-logs"):
            raise ValueError("Unknown storage action")
        lock=gate=None
        marked=stopped=False
        before=None
        error=None
        removed=None
        recovery=False
        try:
            lock=(PRIVATE/"deploy.lock").open("a")
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            before=shutil.disk_usage(STORAGE).free
            if command=="storage-logs":
                from host_logs import prune_postgres,publish_usage
                removed=prune_postgres(STORAGE)
                publish_usage(STORAGE)
            else:
                revision,image=installed()
                if self.git("rev-parse","HEAD")!=revision or image_info(map_build.CURRENT)["Id"]!=image:
                    raise RuntimeError("Исходники и рабочий образ должны совпадать")
                if recent_uploads():
                    raise RuntimeError("Завершите недавние загрузки перед обслуживанием")
                for service in SERVICES:
                    mounts=inspect_container(service).get("Mounts",[])
                    if not any(m.get("Source")==str(CONTROL) and m.get("Destination")=="/run/map-updater"
                               and not m.get("RW") for m in mounts):
                        raise RuntimeError("Не установлен защищённый канал обслуживания")
                MARKER.touch(mode=0o644,exist_ok=False)
                marked=True
                fd=os.open(CONTROL,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
                gate=LOCK.open("rb")
                deadline=time.monotonic()+30
                while True:
                    try:
                        fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic()>=deadline:raise RuntimeError("Есть активные операции; очистка отменена")
                        time.sleep(.25)
                verify_idle()
                if "," in str(STORAGE) or "\n" in str(STORAGE):
                    raise RuntimeError("Неподдерживаемый путь хранения")
                prefix=["docker","compose","--env-file",".env","--env-file",".env.generated"]
                # If stop partially fails, finally still attempts to restore every service.
                stopped=True
                cmd([*prefix,"stop",*SERVICES],cwd=self.project,timeout=120)
                docker("run","--rm","--network","none","--read-only","--user","10001:10001",
                       "--entrypoint","python","-e","MAP_APP_STORAGE_ROOT=/storage/app",
                       "--mount","type=bind,source="+str(STORAGE/"app")+",target=/storage/app",
                       image,"-c","from app.system.technical_cache import clear_disposable; clear_disposable()",
                       timeout=180)
        except Exception as exc:
            error=str(exc)[:250]
        finally:
            if stopped:
                try:
                    cmd([*prefix,"up","-d","--no-build","--wait","--wait-timeout","180",*SERVICES],
                        cwd=self.project,timeout=240)
                    if installed()[0]!=revision:raise RuntimeError("Рабочая ревизия изменилась")
                    check_proxy()
                except Exception:
                    recovery=True
                    error="Не удалось восстановить приложение после обслуживания. Требуется проверка сервера."
            if marked and not recovery:
                MARKER.unlink(missing_ok=True)
                fd=os.open(CONTROL,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(fd)
                finally:os.close(fd)
            if gate is not None:gate.close()
            if lock is not None:lock.close()
            delta=None
            if before is not None:
                try:delta=shutil.disk_usage(STORAGE).free-before
                except OSError:pass
            result={"kind":command,"state":"failed" if error else "completed",
                    "started_at":self.state.get("storage_action",{}).get("started_at"),
                    "finished_at":now(),"removed":removed,"available_delta_bytes":delta,
                    "detail":error or "Обслуживание завершено"}
            fields={"busy":False,"storage_action":result}
            if recovery:fields.update(phase="recovery_required",detail=error)
            self.publish(**fields)

    def update(self,expected):
        locked=gate=None
        switched=False
        marked=False
        warnings=[]
        candidate=None
        try:
            locked=(PRIVATE/"deploy.lock").open("a")
            fcntl.flock(locked,fcntl.LOCK_EX|fcntl.LOCK_NB)
            warnings+=recover_owned_work()
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
            check_proxy()
            before=shutil.disk_usage(self.project).free
            self.publish(phase="building",detail="Сборка нового образа; MAP продолжает работать",
                         free_before=before,free_change=None,warnings=[])
            with tempfile.TemporaryDirectory(prefix="source-",dir=WORKSPACE) as directory:
                archive=Path(directory)/"source.tar"
                with archive.open("wb") as out:
                    subprocess.run(["git","archive","--format=tar",target],cwd=self.project,
                                   stdout=out,check=True,timeout=120)
                subprocess.run(["tar","-xf",str(archive),"-C",directory],check=True,timeout=120)
                archive.unlink()
                candidate="map-local/app:rev-"+target
                warnings+=map_build.build(Path(directory),target,candidate)
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
            old_workers=worker_instances()
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
                    fresh=set(sql("""SELECT instance_id::text FROM service_heartbeats
                           WHERE service IN ('megaloc','thumbnail','cleanup')
                             AND seen_at>now()-interval '35 seconds'""").splitlines())
                    if len(fresh)!=3 or fresh.intersection(old_workers):
                        raise RuntimeError("Нет новых heartbeat всех работников")
                    check_proxy()
                    break
                except (RuntimeError,OSError,ValueError,http.client.HTTPException,subprocess.SubprocessError):
                    if time.monotonic()>=deadline:
                        raise
                    time.sleep(3)
            self.publish(phase="cleanup",detail="Очистка только собственных старых сборок")
            try:
                warnings+=clean_images(target,old)
                warnings+=map_build.clean_owned_builders()
                for path in BACKUPS.glob("backup-*"):
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
            if not switched and candidate:
                try:
                    info=image_info(candidate)
                    if (info["Config"].get("Labels") or {}).get("io.map.project")==PROJECT and not docker("ps","-aq","--filter","ancestor="+info["Id"]):
                        docker("image","rm",candidate)
                except Exception:
                    warnings.append("Проверка временного образа потребуется при следующем обновлении")
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
            if line not in (b"status\n",b"check\n",b"update\n",b"storage-cache\n",b"storage-logs\n"):
                return
            result=self.server.updater.dispatch(line.decode().strip())
            self.wfile.write((json.dumps(result,ensure_ascii=False)+"\n").encode())
        except (OSError,ValueError):
            return

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--project-root",type=Path,required=True)
    parser.add_argument("--storage-root",type=Path,required=True)
    args=parser.parse_args()
    if os.geteuid()!=0:
        parser.error("root required")
    os.umask(0o077)
    project=args.project_root.resolve(strict=True)
    if project.stat().st_uid!=0 or project.stat().st_mode&0o022:
        parser.error("project must be root-owned and not group/world writable")
    configure(args.storage_root,project)
    with (PRIVATE/"deploy.lock").open("a") as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:pass
        else:recover_owned_work()
    socket_path=RPC/"control.sock"
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
