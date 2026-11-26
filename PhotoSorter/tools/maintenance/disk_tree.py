"""Independent root-filesystem census. Never traverses container/other mounts.

Visible inode blocks, sampled unlinked files and the kernel used-byte counter
are distinct observations; their remainder is not assigned to a made-up owner.
"""
from pathlib import Path
import os
import re
import stat
import time
from storage_tree import measure_tree

def mounts():
    result={}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left,right=line.split(" - ",1)
        fields=left.split()
        name=re.sub(r"\\([0-7]{3})",lambda m:chr(int(m[1],8)),fields[4])
        result[Path(name)]={"device":fields[2],"id":fields[0],"filesystem":right.split()[0]}
    return result

def capacity(root):
    fs=os.statvfs(root)
    return {"total_bytes":fs.f_blocks*fs.f_frsize,"used_bytes":(fs.f_blocks-fs.f_bfree)*fs.f_frsize,
            "available_bytes":fs.f_bavail*fs.f_frsize,
            "filesystem_reserved_free_bytes":(fs.f_bfree-fs.f_bavail)*fs.f_frsize}

def deleted_open(device,*,proc=Path("/proc"),limit=50000,seconds=5):
    """Lower bound on unlinked regular files still accessible through FDs.
    Memory mappings and inaccessible namespaces may hold other allocations.
    """
    report={"allocated_bytes":0,"files":0,"entries":0,"errors":0,"limit_reached":False,
            "partial":True,"basis":"same_device_unlinked_regular_file_descriptors_lower_bound"}
    seen=set();deadline=time.monotonic()+seconds
    try:
        with os.scandir(proc) as processes:
            for process in processes:
                if not process.name.isdecimal():continue
                try:
                    with os.scandir(Path(process.path)/"fd") as entries:
                        for entry in entries:
                            if report["entries"]>=limit or time.monotonic()>=deadline:
                                report["limit_reached"]=True
                                return report
                            report["entries"]+=1
                            try:
                                st=os.stat(entry.path)
                                if st.st_dev!=device or st.st_nlink!=0 or not stat.S_ISREG(st.st_mode):continue
                                ident=(st.st_dev,st.st_ino)
                                if ident not in seen:
                                    seen.add(ident)
                                    report["files"]+=1
                                    report["allocated_bytes"]+=st.st_blocks*512
                            except FileNotFoundError:pass
                            except OSError:report["errors"]+=1
                except FileNotFoundError:pass
                except OSError:report["errors"]+=1
    except OSError:report["errors"]+=1
    return report

def measure_disk(storage,engine,*,root=Path("/"),mount_reader=mounts,deleted_sampler=deleted_open,limit=1000000,seconds=45):
    root=Path(root)
    paths={}
    roots={}
    def add(name,path):
        if not path:return
        try:
            path=Path(path)
            relative=path.relative_to(root).parts
            if not relative or ".." in relative or not path.is_absolute():return
            # Classify only an observed path. A symlink is counted as a node,
            # never followed into another scope or filesystem.
            if relative in roots:return
            if not path.exists() and not path.is_symlink():return
            roots[relative]=name
            paths[name]=str(path)
        except (ValueError,OSError,TypeError):return
    add("map_storage",storage)
    if engine.get("available"):add("docker_engine",engine.get("root"))
    # Default path only: not a claim about a custom containerd daemon root.
    add("containerd_default",root/"var/lib/containerd")
    add("system_logs",root/"var/log")
    before=capacity(root)
    mount_before=mount_reader()
    excluded={p.relative_to(root).parts for p in mount_before if p!=root and p.is_relative_to(root)}
    tree=measure_tree(root,limit=limit,seconds=seconds,scope_roots=roots,
                      default_scope="other_visible",excluded=excluded)
    deleted=deleted_sampler(os.stat(root).st_dev)
    after=capacity(root)
    mount_changed=mount_before!=mount_reader()
    comparable=not tree["partial"] and not mount_changed and before["used_bytes"]==after["used_bytes"]
    tree.update(capacity_before=before,capacity_after=after,paths=paths,
                filesystem=mount_before.get(root,{}).get("filesystem"),mount_table_changed=mount_changed,
                deleted_open=deleted,comparable=comparable,
                residual_bytes=after["used_bytes"]-tree["allocated_bytes"]-deleted["allocated_bytes"],
                basis="root_filesystem_visible_inode_blocks_plus_sampled_unlinked_fds; not_atomic_or_extent_accounting")
    # Residual includes inaccessible/covered paths, filesystem-internal
    # allocations, live changes and omitted unlinked objects. Never infer them.
    return tree
