"""Create a fresh storage V2 layout without following symlinks or reowning data."""
import argparse
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.storage.categories import APP_UID, APP_GID, LAYOUT_VERSION, BOOTSTRAP_DIRS, APP_BOOTSTRAP_DIRS
from app.storage.config import absolute_root

APP_DIRS = APP_BOOTSTRAP_DIRS
PRIVATE_DIRS = tuple(folder for folder in BOOTSTRAP_DIRS if not folder.startswith("app/"))

def ensure_directory(path, uid, gid, mode):
    try:
        path.mkdir(mode=mode)
    except FileExistsError:
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_gid != gid or stat.S_IMODE(info.st_mode) != mode:
            raise ValueError(f"Unsafe existing storage directory: {path}")
    else:
        os.chown(path, uid, gid, follow_symlinks=False)
        os.chmod(path, mode)

def bootstrap(root, *, host_uid=0, host_gid=0, app_uid=APP_UID, app_gid=APP_GID):
    root = absolute_root(root)
    if not root.parent.is_dir():
        raise ValueError("Storage root parent must already exist")
    ensure_directory(root, host_uid, host_gid, 0o750)
    marker = root / "system/state/layout-version"
    for ancestor in (root / "system", marker.parent):
        if ancestor.is_symlink():
            raise ValueError("Symlinked layout marker parent")
    if marker.is_symlink():
        raise ValueError("Symlinked layout marker")
    if marker.exists():
        info = marker.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != host_uid or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Unsafe storage layout marker")
        if marker.read_text().strip() != str(LAYOUT_VERSION):
            raise ValueError("Incompatible storage layout")
    elif any(root.iterdir()):
        raise ValueError("Nonempty unmarked storage root; refusing initialization")
    for rel in PRIVATE_DIRS:
        path = root
        for part in Path(rel).parts:
            path = path / part
            ensure_directory(path, host_uid, host_gid, 0o700)
    ensure_directory(root / "app", app_uid, app_gid, 0o750)
    for rel in APP_DIRS:
        path = root / "app"
        for part in Path(rel).parts:
            path = path / part
            ensure_directory(path, app_uid, app_gid, 0o750)
    if not marker.exists():
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(str(LAYOUT_VERSION) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(marker.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Storage bootstrap requires root")
    bootstrap(args.root)

if __name__ == "__main__":
    main()
