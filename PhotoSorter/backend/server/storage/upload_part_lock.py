"""Per-part append/receipt coordination, without a new disk marker or global IO lock."""
from contextlib import contextmanager
import fcntl
import os
import stat
from pathlib import Path
from app.storage.filesystem import parent_fd

@contextmanager
def _part_fd(root,relative):
    with parent_fd(root,relative) as (parent,name):
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError("Invalid upload part")
            yield fd
        finally:os.close(fd)

@contextmanager
def writing_part(root,path):
    with _part_fd(root,Path(path).relative_to(root)) as fd:
        fcntl.flock(fd,fcntl.LOCK_EX)
        yield

def plausible_inflight_append(root,key,observed,received,declared):
    # A shorter-than-receipt or oversized part is never excused by an active writer.
    if not received<observed.st_size<=declared:return False
    try:
        with _part_fd(root,Path(key[4:])) as fd:
            current=os.fstat(fd)
            if (current.st_dev,current.st_ino)!=(observed.st_dev,observed.st_ino):return False
            if not received<current.st_size<=declared:return False
            try:fcntl.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError:return True
            return False
    except (OSError,ValueError):return False
