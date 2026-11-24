"""Remove batch-owned paths in measurable units without following symlinks."""
from __future__ import annotations

import os
import shutil
import stat

from .paths import batch_dir,batch_root,part_path,normalized_dir,owned_directory,owned_file,run_dir
from app import config
from app.storage.paths import managed_path,managed_prefix,run_key
from app.storage.categories import Category


def remove_batch_files(batch_id,run_ids,upload_ids,data_dir,runs_dir,report):
    # Run trees (including the ZIP), temporary parts and individual originals.
    trees=[owned_directory(run_dir(run_id),config.APP_STORAGE_ROOT) for run_id in run_ids]
    trees.extend(owned_directory(runs_dir/run_key(run_id),runs_dir) for run_id in run_ids)
    trees=[path for path in trees if path.exists()]
    incoming=managed_prefix(Category.FO_UPLOAD_PART,batch_uuid=batch_id)
    parts=[owned_file(part_path(batch_id,upload_id),config.APP_STORAGE_ROOT) for upload_id in upload_ids]
    parts=[path for path in parts if path.exists()]
    originals=owned_directory(batch_dir(batch_id),config.APP_STORAGE_ROOT)
    extra=[normalized_dir(batch_id),*[managed_path(Category.TRANSCODE_TEMP,task_id=u) for u in upload_ids],
           *[managed_path(category,run_id=r) for r in run_ids for category in (Category.VIDEO_FRAMES,Category.PROCESSING_STAGING)]]
    trees.extend(path for path in (owned_directory(p,config.APP_STORAGE_ROOT) for p in extra) if path.exists())
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
        # Empty batch/transfer containers have no user data of their own.
        for folder in (incoming,batch_root(batch_id)/"results",batch_root(batch_id)):
            try:folder.rmdir()
            except FileNotFoundError:pass
        return total
    finally:
        if fd is not None:
            os.close(fd)
