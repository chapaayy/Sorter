"""Create/check fresh storage V2 without following symlinks or reowning data."""
import argparse
import json
from contextlib import contextmanager, ExitStack
import fcntl
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.storage.categories import APP_UID, APP_GID, LAYOUT_VERSION, BOOTSTRAP_DIRS, APP_BOOTSTRAP_DIRS, CONTRACT_PATH
from app.storage.config import absolute_root
from app.storage.filesystem import directory_fd

POLICY=json.loads(CONTRACT_PATH.read_text())
APP_DIRS = APP_BOOTSTRAP_DIRS
PRIVATE_DIRS = tuple(folder for folder in BOOTSTRAP_DIRS if not folder.startswith("app/"))
_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

@contextmanager
def child_directory(parent, name, uid, gid, mode, *, create):
    created = False
    if create:
        try:
            os.mkdir(name, mode=mode, dir_fd=parent)
            created = True
        except FileExistsError:
            pass
    fd = os.open(name, _DIR, dir_fd=parent)
    try:
        if created:
            os.fchown(fd, uid, gid)
            os.fchmod(fd, mode)
            os.fsync(parent)
        info = os.fstat(fd)
        if info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
            raise ValueError(f"Unsafe existing storage directory: {name}")
        yield fd
    finally:
        os.close(fd)

@contextmanager
def walk_directory(root, relative, uid, gid, mode, *, create):
    with ExitStack() as stack:
        fd = root
        for part in Path(relative).parts:
            fd = stack.enter_context(child_directory(fd, part, uid, gid, mode, create=create))
        yield fd

def read_marker(root, uid, gid):
    try:
        with walk_directory(root, "system/state", uid, gid, 0o700, create=False) as parent:
            fd = os.open("layout-version", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         dir_fd=parent)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_gid != gid
                        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                    raise ValueError("Unsafe storage layout marker")
                version = os.read(fd, 32).decode("ascii").strip()
                if version != str(LAYOUT_VERSION):
                    raise ValueError("Incompatible storage layout")
            finally:
                os.close(fd)
    except FileNotFoundError:
        return False
    return True

def bootstrap(root, *, host_uid=0, host_gid=0, app_uid=APP_UID, app_gid=APP_GID, check=False):
    root = absolute_root(root)
    if not root.parent.is_dir():
        raise ValueError("Storage root parent must already exist")
    with directory_fd(root.parent) as parent:
        with child_directory(parent, root.name, host_uid, host_gid, 0o750, create=not check) as root_fd:
            # The stable directory inode is the installation lock. No lock files
            # in app-writable paths; no pathname reopening during privileged walk.
            fcntl.flock(root_fd, fcntl.LOCK_SH if check else fcntl.LOCK_EX)
            marked = read_marker(root_fd, host_uid, host_gid)
            if not marked and (check or os.listdir(root_fd)):
                raise ValueError("Nonempty or missing unmarked storage root; refusing initialization")
            # Parents are host-private. Only exact bind-mount leaves have
            # native service ownership; never recursively chown PGDATA.
            native=POLICY["infrastructure_owners"]["postgres"]
            pg_uid,pg_gid=(native["uid"],native["gid"]) if host_uid==0 else (host_uid,host_gid)
            for rel in sorted(set(PRIVATE_DIRS),key=lambda p:(len(Path(p).parts),p)):
                parts=Path(rel).parts
                with ExitStack() as stack:
                    fd=root_fd
                    for n,part in enumerate(parts,1):
                        key="/".join(parts[:n])
                        uid,gid,mode=host_uid,host_gid,0o700
                        if key=="infrastructure/postgres/data":uid,gid=pg_uid,pg_gid
                        if key=="logs/postgres":uid,gid=pg_uid,pg_gid
                        if key in ("logs/api","logs/worker","logs/cleanup","logs/thumbnail","logs/processing","logs/models"):
                            uid,gid=app_uid,app_gid
                        if key in ("system/updater/control","system/updater/rpc"):mode=0o755
                        fd=stack.enter_context(child_directory(fd,part,uid,gid,mode,create=not check))
            with child_directory(root_fd, "app", app_uid, app_gid, 0o750, create=not check) as app_fd:
                for rel in APP_DIRS:
                    with walk_directory(app_fd, rel, app_uid, app_gid, 0o750, create=not check):
                        pass
            with walk_directory(root_fd,"system/state",host_uid,host_gid,0o700,create=False) as state:
                branch=POLICY["update_branch"].encode()+b"\n"
                try:
                    fd=os.open("update-branch",os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=state)
                except FileNotFoundError:
                    if check:raise
                    fd=os.open("update-branch",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=state)
                    with os.fdopen(fd,"wb") as stream:
                        stream.write(branch);stream.flush();os.fsync(stream.fileno())
                    os.fsync(state)
                else:
                    with os.fdopen(fd,"rb") as stream:
                        st=os.fstat(stream.fileno())
                        if st.st_uid!=host_uid or stat.S_IMODE(st.st_mode)!=0o600 or stream.read(128)!=branch:
                            raise ValueError("Invalid installation branch pin")
            with directory_fd(root,"system/updater/control") as control:
                if not check:
                    fd=os.open("activity.lock",os.O_CREAT|os.O_RDONLY|os.O_NOFOLLOW,0o644,dir_fd=control)
                    os.close(fd)
            if not marked:
                with walk_directory(root_fd, "system/state", host_uid, host_gid, 0o700, create=False) as state:
                    fd = os.open("layout-version", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o600, dir_fd=state)
                    with os.fdopen(fd, "w") as stream:
                        stream.write(str(LAYOUT_VERSION) + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.fsync(state)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Storage bootstrap requires root")
    bootstrap(args.root, check=args.check)

if __name__ == "__main__":
    main()
