"""Remove batch-owned paths in measurable units without following symlinks."""
from __future__ import annotations

import os
import shutil
import stat

from .paths import batch_dir,owned_directory,owned_file,run_dir


def remove_batch_files(batch_id,run_ids,upload_ids,data_dir,runs_dir,report):
    # Run trees (including the ZIP), temporary parts and individual originals.
    trees=[owned_directory(run_dir(run_id,root),root) for run_id in run_ids
           for root in (data_dir/"outputs",runs_dir)]
    trees=[path for path in trees if path.exists()]
    incoming=data_dir/"incoming"
    parts=[owned_file(incoming/f"{upload_id}.part",incoming) for upload_id in upload_ids]
    parts=[path for path in parts if path.exists()]
    originals=owned_directory(batch_dir(batch_id),data_dir/"uploads")
    try:
        fd=os.open(originals,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    except FileNotFoundError:
        fd=None
    try:
        names=os.listdir(fd) if fd is not None else []
        # Keep the final directory removal and DB commit as separate units.
        total=len(trees)+len(parts)+len(names)+(fd is not None)+1
        done=0
        report("files",done,total)
        for path in trees:
            shutil.rmtree(path)
            done+=1
            report("files",done,total)
        for path in parts:
            path.unlink(missing_ok=True)
            done+=1
            report("files",done,total)
        if fd is not None:
            for name in names:
                try:
                    info=os.stat(name,dir_fd=fd,follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        shutil.rmtree(name,dir_fd=fd)
                    else:
                        os.unlink(name,dir_fd=fd)
                except FileNotFoundError:
                    pass
                done+=1
                report("files",done,total)
            originals.rmdir()
            done+=1
            report("files",done,total)
        return total
    finally:
        if fd is not None:
            os.close(fd)
