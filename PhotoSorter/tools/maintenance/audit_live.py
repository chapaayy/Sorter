#!/usr/bin/env python3
"""Append-only, read-only Linux inotify event history for MAP storage.

Watches existing MAP directories and the writable overlay upperdirs of its
running Docker containers. It also observes container /tmp views and selected
host temp roots. All observations are metadata only, not source file contents.
The audit is NOT syscall-complete (e.g. O_TMPFILE, inotify watch races, queue
overflow); gaps are recorded and visible to the user.
"""
from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import select
import signal
import stat
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Linux <sys/inotify.h> values.
IN_MODIFY = 0x00000002
IN_CLOSE_WRITE = 0x00000008
IN_ATTRIB = 0x00000004
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ISDIR = 0x40000000
MASK = (IN_MODIFY | IN_CLOSE_WRITE | IN_ATTRIB | IN_MOVED_FROM | IN_MOVED_TO | IN_CREATE |
        IN_DELETE | IN_DELETE_SELF | IN_MOVE_SELF | IN_Q_OVERFLOW)
HEADER = struct.Struct("iIII")

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def within(path: Path, root: Path):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

def docker_containers(project_name: str):
    def call(*args):
        return subprocess.run(["docker", *args], capture_output=True, text=True,
                              timeout=12, check=True).stdout
    ids = call("ps", "-q", "--filter", "label=com.docker.compose.project=" + project_name).split()
    return json.loads(call("inspect", *ids)) if ids else []

def overlay_upper_paths(container, proc_root: Path):
    try:
        from importlib.util import spec_from_file_location, module_from_spec
        path = Path(__file__).with_name("audit_containerd.py")
        spec = spec_from_file_location("map_live_containerd", path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        pid = int(container.get("State", {}).get("Pid") or 0)
        if pid < 1:
            return []
        raw = (proc_root / str(pid) / "mountinfo").read_text(encoding="utf-8")
        return [Path(path) for role, path in module.overlay_paths(raw) if role == "upper"]
    except (OSError, TypeError, ValueError) as exc:
        return []

class LiveAudit:
    def __init__(self, project: Path, *, roots=None, project_name="outdoor-sorter",
                 proc_root=Path("/proc"), rediscover_seconds=10,
                 containers_fn=docker_containers, storage=None, duration=60, max_bytes=90*1024*1024):
        self.project = Path(project).resolve(strict=True)
        self.project_name = project_name
        self.proc_root = Path(proc_root)
        self.containers_fn = containers_fn
        self.rediscover_seconds = rediscover_seconds
        self.storage=Path(storage) if storage else self.project/"storage"
        self.report=self.storage/"logs/audit"
        self.duration=min(300,max(1,duration))
        self.max_bytes=min(90*1024*1024,max_bytes)
        self.written=0
        self.deadline=time.monotonic()+self.duration
        self.primary_roots = list(roots) if roots is not None else [
            self.storage/"app",
        ]
        self.skip_root = self.report
        self.wd_paths = {}
        self.path_wds = {}
        self.live_roots = {}
        self.total = 0
        self.overflows = 0
        self.watch_errors = 0
        self.events_by_type = {}
        self.sizes = {}
        self.last_modify = {}
        self.shm_batches = {}
        self.shm_close_writes_observed = 0
        self.last_shm_flush = time.monotonic()
        self.started_at = utcnow()
        self.last_event_at = None
        self.last_discovery = 0
        self.last_state = 0
        self.state_error = []
        self.stop = False
        self.fd = None
        self.stream = None

    def root_scope(self, root: Path):
        return ("map_updater" if root in (Path("/var/lib/map-updater"), Path("/usr/local/lib/map-updater")) else
                "map" if within(root, self.project) else
                "container" if "containerd" in root.parts or "root" in root.parts else
                "shared_unattributed")

    def should_skip(self, path: Path):
        return within(path, self.skip_root)

    def init(self):
        library = ctypes.CDLL(None, use_errno=True)
        init = library.inotify_init1
        init.argtypes = [ctypes.c_int]
        init.restype = ctypes.c_int
        fd = init(os.O_NONBLOCK | os.O_CLOEXEC)
        if fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        self.fd = fd
        self.add_watch = library.inotify_add_watch
        self.add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self.add_watch.restype = ctypes.c_int
        if self.report.is_symlink() or self.report.resolve(strict=False)!=self.report:
            raise RuntimeError("Audit event output path is not safe")
        self.report.mkdir(parents=True, exist_ok=True)
        self.stream=(self.report/"live-events.jsonl").open("w",encoding="utf-8",buffering=1)
        os.chmod(self.report/"live-events.jsonl",0o644)
        self.emit("observer_started", path=str(self.project), scope="system")

    def emit(self, kind, *, path, scope, **details):
        record = {"time_utc": utcnow(), "event": kind, "path": path, "scope": scope}
        record.update(details)
        if self.stream:
            line=json.dumps(record,ensure_ascii=False,separators=(",",":"))+"\n"
            size=len(line.encode("utf8"))
            if self.written+size>self.max_bytes:
                self.stop=True
                return
            self.stream.write(line)
            self.written+=size
        self.total += 1
        self.events_by_type[kind] = self.events_by_type.get(kind, 0) + 1
        self.last_event_at = record["time_utc"]

    def batch_postgres_shared_memory_close(self, *, path: Path, scope: str,
                                           size, allocated, inode) -> bool:
        """Compact repeated closes of one PostgreSQL tmpfs object only.

        Keep every create/delete/resize/rename and every other file as before.
        Exact close counts + first/last timestamp are retained in the log.
        """
        if ("/root/dev/shm/PostgreSQL." not in str(path)
                or not scope.startswith("map_container_tmp:")
                or "postgres" not in scope
                or size is None or inode is None):
            return False
        moment = utcnow()
        key = (str(path), scope, inode, size, allocated)
        batch = self.shm_batches.get(key)
        if batch is None:
            self.shm_batches[key] = {
                "path": str(path), "scope": scope, "count": 1,
                "first_seen_utc": moment, "last_seen_utc": moment,
                "inode": inode, "logical_bytes": size, "allocated_bytes": allocated,
            }
        else:
            batch["count"] += 1
            batch["last_seen_utc"] = moment
        self.shm_close_writes_observed += 1
        self.last_event_at = moment
        return True

    def flush_shm_batches(self):
        if not self.shm_batches:
            return
        for batch in self.shm_batches.values():
            self.emit(
                "postgres_shm_close_write_summary",
                path=batch["path"], scope=batch["scope"],
                observed_close_writes=batch["count"],
                first_seen_utc=batch["first_seen_utc"],
                last_seen_utc=batch["last_seen_utc"],
                logical_bytes=batch["logical_bytes"],
                allocated_bytes=batch["allocated_bytes"], inode=batch["inode"],
            )
        self.shm_batches.clear()
        self.last_shm_flush = time.monotonic()

    def watch_tree(self, root: Path, scope: str):
        """Watch existing dirs; new dirs receive a watch as soon as observed."""
        root = Path(root)
        if self.should_skip(root) or not root.is_dir():
            return
        stack = [root]
        while stack:
            if self.stop or time.monotonic()>=self.deadline or len(self.path_wds)>=100000:
                self.stop=True
                return
            current = stack.pop()
            if self.should_skip(current) or current in self.path_wds:
                continue
            if current.is_symlink():
                # /proc/PID/root/... contains symlink ancestors; the leaf is real.
                continue
            code = self.add_watch(self.fd, os.fsencode(current), MASK)
            if code < 0:
                self.watch_errors += 1
                if len(self.state_error) < 100:
                    err = ctypes.get_errno()
                    self.state_error.append("Cannot watch " + str(current) + ": errno " + str(err))
                continue
            # A second path can refer to the very same directory inode.
            # Never lose the first canonical scope when watches are shared.
            if code not in self.wd_paths:
                self.wd_paths[code] = (current, scope)
            self.path_wds[current] = code
            try:
                with os.scandir(current) as iterator:
                    children = [Path(item.path) for item in iterator
                                if item.is_dir(follow_symlinks=False)]
                stack.extend(children)
            except OSError as exc:
                self.watch_errors += 1
                if len(self.state_error) < 100:
                    self.state_error.append("Cannot scan directory " + str(current) + ": " + str(exc)[:120])

    def discover(self):
        roots = [(Path(root), self.root_scope(Path(root))) for root in self.primary_roots]
        try:
            containers = self.containers_fn(self.project_name)
            for container in containers:
                name = container.get("Name", "").lstrip("/") or container.get("Id", "")[:12]
                pid = int(container.get("State", {}).get("Pid") or 0)
                if pid > 0:
                    for path in overlay_upper_paths(container, self.proc_root):
                        roots.append((path, "map_container_upper:" + name))
                    for rel in ("tmp", "var/tmp", "dev/shm"):
                        path = self.proc_root / str(pid) / "root" / rel
                        if path.is_dir():
                            roots.append((path, "map_container_tmp:" + name))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            self.watch_errors += 1
            if len(self.state_error) < 100:
                self.state_error.append("Docker discovery failed: " + type(exc).__name__)
        for path, scope in roots:
            if path.is_dir() and path not in self.live_roots:
                self.watch_tree(path, scope)
                self.live_roots[path] = scope
        self.last_discovery = time.monotonic()

    def process(self, raw: bytes):
        cursor = 0
        while cursor + HEADER.size <= len(raw):
            wd, mask, cookie, nlen = HEADER.unpack_from(raw, cursor)
            cursor += HEADER.size
            if cursor + nlen > len(raw):
                self.watch_errors += 1
                self.state_error.append("Truncated inotify event buffer")
                break
            name = os.fsdecode(raw[cursor:cursor+nlen].split(b"\x00", 1)[0])
            cursor += nlen
            if mask & IN_Q_OVERFLOW:
                self.overflows += 1
                self.emit("queue_overflow", path="", scope="system",
                          lost_event_count="unknown")
                continue
            pair = self.wd_paths.get(wd)
            if not pair:
                continue
            root, scope = pair
            path = root / name if name else root
            if self.should_skip(path):
                continue
            if mask & IN_IGNORED:
                self.wd_paths.pop(wd, None)
                self.path_wds.pop(root, None)
                continue
            if (mask & (IN_CREATE | IN_MOVED_TO)) and (mask & IN_ISDIR):
                self.watch_tree(path, scope)
            kind = None
            for bit, label in (
                (IN_CREATE, "create"),(IN_MODIFY,"modify"),(IN_CLOSE_WRITE,"close_write"),
                (IN_MOVED_FROM,"move_from"),(IN_MOVED_TO,"move_to"),
                (IN_DELETE,"delete"),(IN_DELETE_SELF,"delete_self"),
                (IN_MOVE_SELF,"move_self"),(IN_ATTRIB,"attribute"),
            ):
                if mask & bit:
                    kind = label
                    break
            if kind is None:
                continue
            if kind == "modify":
                # Record changing temporary sizes while limiting high-frequency
                # write() storms to at most one observation per file/second.
                moment=time.monotonic()
                if moment-self.last_modify.get(str(path),-1e9)<1.0:
                    continue
                self.last_modify[str(path)]=moment
            size = None
            allocated = None
            inode = None
            if kind not in ("delete","move_from","delete_self"):
                try:
                    meta = path.lstat()
                    if stat.S_ISREG(meta.st_mode):
                        size, allocated, inode = meta.st_size, meta.st_blocks*512, meta.st_ino
                        self.sizes[str(path)] = (size, allocated)
                except OSError:
                    pass
            if kind == "close_write" and self.batch_postgres_shared_memory_close(
                    path=path, scope=scope, size=size, allocated=allocated, inode=inode):
                continue
            previous = self.sizes.get(str(path))
            self.emit(kind, path=str(path), scope=scope,
                      is_directory=bool(mask & IN_ISDIR),cookie=cookie or None,
                      logical_bytes=size,allocated_bytes=allocated,
                      last_seen_bytes=previous[0] if previous else None,inode=inode)
            if kind in ("delete","move_from","delete_self"):
                self.sizes.pop(str(path), None)
                self.last_modify.pop(str(path), None)

    def state(self, *, running=True):
        state = {
            "schema":"map-live-audit-v1",
            "running":running,
            "started_at":self.started_at,
            "heartbeat_at":utcnow(),
            "last_event_at":self.last_event_at,
            "events":self.total,
            "events_by_type":self.events_by_type,
            "postgres_shm_close_writes_aggregated":self.shm_close_writes_observed,
            "postgres_shm_pending":sum(b["count"] for b in self.shm_batches.values()),
            "events_observed_including_aggregates":(
                self.total + self.shm_close_writes_observed -
                self.events_by_type.get("postgres_shm_close_write_summary", 0)
            ),
            "queue_overflows":self.overflows,
            "watch_errors":self.watch_errors,
            "watched_directories":len(self.wd_paths),
            "watched_roots":[{"path":str(x),"scope":y} for x,y in self.live_roots.items()],
            "warnings":self.state_error,
            "limitations":[
                "inotify does not report the PID of a file write.",
                "Temporary unnamed O_TMPFILE objects and files created before monitoring cannot be reconstructed.",
                "New-directory watch races, cross-mount events and queue overflows can miss events.",
                "Host /tmp observations are shared and cannot be attributed solely to MAP.",
                "Records include file metadata only and do not measure every write() syscall.",
                "Repeated close_write on PostgreSQL /dev/shm shared memory is aggregated in 60-second groups; individual closes are not retained, but exact counts and observed sizes are.",
            ],
        }
        temp = self.report / ".live-state.tmp"
        temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")
        os.chmod(temp,0o644)
        os.replace(temp,self.report/"live-state.json")
        self.last_state=time.monotonic()
        return state

    def run(self):
        self.init()
        try:
            self.discover()
            self.state()
            while not self.stop and time.monotonic()<self.deadline:
                if time.monotonic()-self.last_discovery >= self.rediscover_seconds:
                    self.discover()
                if self.fd is None:
                    break
                ready,_,_ = select.select([self.fd],[],[],1.0)
                if ready:
                    while not self.stop and time.monotonic()<self.deadline:
                        try:
                            data = os.read(self.fd,1024*1024)
                        except BlockingIOError:
                            break
                        if not data:
                            break
                        self.process(data)
                if time.monotonic()-self.last_shm_flush>=60:
                    self.flush_shm_batches()
                if time.monotonic()-self.last_state>=5:
                    self.state()
        finally:
            self.flush_shm_batches()
            self.emit("observer_stopped",path=str(self.project),scope="system")
            self.state(running=False)
            if self.stream:
                self.stream.close()
            if self.fd is not None:
                os.close(self.fd)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root",type=Path,required=True)
    parser.add_argument("--project-name",default="outdoor-sorter")
    args=parser.parse_args()
    if os.geteuid()!=0:
        parser.error("Host event observation requires root")
    from snapshot import configured_storage_root
    import fcntl
    storage=configured_storage_root(args.project_root.resolve())
    lock=(storage/"logs/audit/observer.lock").open("a")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    observer=LiveAudit(args.project_root,project_name=args.project_name,storage=storage)
    def shutdown(_signal,_frame):
        observer.stop=True
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    try:observer.run()
    finally:lock.close()

if __name__=="__main__":
    main()
