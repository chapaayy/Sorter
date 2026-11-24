"""Consistent, *operator-quiesced* PhotoSorter archive and safe disposable restore.

No Docker stop/start, schema migration, live deployment or destructive cleanup here.
Requires PostgreSQL pg_dump/pg_restore/psql clients matching the DB major version.
This archive is sensitive: .env.generated, originals and model caches. Encrypt offsite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit,unquote

INCLUDED_DIRS=("storage/app","storage/infrastructure/caddy/data","storage/infrastructure/caddy/config")
# No live PGDATA copy; PostgreSQL uses a verified logical dump. Transient
# archives and scratch, logs and updater workspaces are reproducible/excluded.
EXCLUDED_PREFIXES=tuple("storage/app/temporary/"+part+"/" for part in
                   ("archives","scratch","model-downloads","transcoding","video-frames","processing"))
MODEL_DIRS=("storage/app/models","storage/app/cache")
INCLUDED_FILES=(".env",".env.generated","compose.yaml","PhotoSorter/docker/caddy/Caddyfile","storage/system/state/layout-version","storage/system/state/update-branch","storage/system/state/log-policy.json")
SCHEMA_VERSION=3
BLOCK=1024*1024

def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(BLOCK),b""):h.update(chunk)
    return h.hexdigest()

def pg_env(url):
    data=urlsplit(url)
    if data.scheme not in ("postgres","postgresql") or not data.hostname or not data.path.strip("/"):
        raise ValueError("Expected postgresql://user:password@host:port/database")
    env=os.environ.copy()
    env.update({
        "PGHOST":data.hostname,
        "PGPORT":str(data.port or 5432),
        "PGUSER":unquote(data.username or ""),
        "PGDATABASE":unquote(data.path.lstrip("/")),
        "PGPASSWORD":unquote(data.password or ""),
        "PGCONNECT_TIMEOUT":"8",
        "PGOPTIONS":"-c statement_timeout=120000"
    })
    if not env["PGUSER"] or not env["PGPASSWORD"]:raise ValueError("DB URL must include a user/password")
    return env

def pg_run(args,url,*,capture=False):
    env=pg_env(url)
    if os.environ.get("MAP_SNAPSHOT_COMPOSE_PG")=="1":
        return compose_pg_run(args,env,capture=capture)
    # Never place plaintext DB URL/password in child process argv or log output.
    return subprocess.run(args,env=env,check=True,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.PIPE)

def compose_pg_run(args,env,*,capture=False):
    """Explicit root-only local Compose client transport; no published DB port."""
    if os.geteuid()!=0 or env["PGHOST"]!="postgres" or env["PGUSER"]!="sorter":
        raise ValueError("Compose snapshot requires root and the local MAP PostgreSQL service")
    db=env["PGDATABASE"]
    if db!="sorter" and not re.fullmatch(r"sorter_restore_[a-z0-9_]+",db):
        raise ValueError("Unexpected database")
    ids=subprocess.check_output(["docker","ps","-q","--filter","label=com.docker.compose.project=outdoor-sorter",
                                 "--filter","label=com.docker.compose.service=postgres"],text=True).splitlines()
    if len(ids)!=1 or not re.fullmatch(r"[0-9a-f]{12,64}",ids[0]):
        raise ValueError("Expected one local PostgreSQL container")
    client=args[0]
    prefix=["docker","exec","-i",ids[0],client,"-U","sorter"]
    if client=="pg_dump":
        if args[1:5]!=["--format=custom","--no-owner","--no-acl","--file"] or len(args)!=6:
            raise ValueError("Unexpected dump arguments")
        with open(args[5],"xb") as out:
            return subprocess.run(prefix+["-d",db,*args[1:4]],stdout=out,stderr=subprocess.PIPE,check=True)
    if client=="pg_restore":
        if db=="sorter" or args[1:6]!=["--exit-on-error","--no-owner","--no-acl","--dbname",db] or len(args)!=7:
            raise ValueError("Restore requires a dedicated staging DB")
        with open(args[6],"rb") as src:
            return subprocess.run(prefix+args[1:6],stdin=src,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
    if client=="psql" and capture:
        return subprocess.run(prefix+["-d",db,"-v","ON_ERROR_STOP=1",*args[1:]],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    raise ValueError("Unexpected local client operation")

def validate_rel(name):
    posix=PurePosixPath(name)
    if not name or posix.is_absolute() or any(p in ("..",".","") for p in name.split("/")) or chr(0) in name or "\\" in name:
        raise ValueError("Unsafe backup member")
    if any(name.startswith(p) for p in EXCLUDED_PREFIXES):raise ValueError("Transient backup member")
    if not (any(name==d or name.startswith(d+"/") for d in INCLUDED_DIRS)
            or name in INCLUDED_FILES):
        raise ValueError("Unexpected backup member: "+name)
    return posix

def safe_model_symlink(name,target):
    """Only relative symlinks inside storage/app/cache or storage/app/models are preserved.

    Hugging Face snapshot refs commonly link to ../../blobs/<sha> inside its cache.
    Block symlinks in user photographs/secret config and links out of Models.
    """
    if (not any(name.startswith(prefix+"/") for prefix in MODEL_DIRS) or not target or
            posixpath.isabs(target) or chr(92) in target or chr(0) in target):
        raise ValueError("Unsafe model symlink")
    destination=posixpath.normpath(posixpath.join(posixpath.dirname(name),target))
    if not any(destination.startswith(prefix+"/") for prefix in MODEL_DIRS):
        raise ValueError("Model symlink escapes model storage")
    return target

def configured_storage_root(root):
    config=root/".env.generated"
    if config.is_symlink() or not config.is_file():
        raise ValueError("Missing protected generated configuration")
    pins=[line.split("=",1)[1] for line in config.read_text().splitlines() if line.startswith("MAP_STORAGE_ROOT=")]
    if len(pins)!=1:
        raise ValueError("Missing or duplicate V2 storage root pin")
    storage=Path(pins[0])
    if not storage.is_absolute() or storage.resolve()!=storage or storage==Path("/"):
        raise ValueError("Unsafe storage root")
    marker=storage/"system/state/layout-version"
    if marker.resolve()!=marker or not marker.is_file() or marker.read_text().strip()!="2":
        raise ValueError("Invalid storage layout marker")
    return storage

def enumerate_files(root,storage):
    files=[]
    for rel in INCLUDED_DIRS:
        folder=storage/rel.removeprefix("storage/")
        if folder.is_symlink() or not folder.is_dir() or folder.resolve()!=folder:
            raise ValueError("Missing or symlinked backup directory: "+rel)
        for path in sorted(folder.rglob("*")):
            name=rel+"/"+path.relative_to(folder).as_posix()
            if any(name.startswith(p) for p in EXCLUDED_PREFIXES):continue
            if path.is_symlink():
                safe_model_symlink(name,os.readlink(path))
                if not any(path.resolve(strict=True).is_relative_to(storage/prefix.removeprefix("storage/")) for prefix in MODEL_DIRS):
                    raise ValueError("Model symlink outside protected model/cache roots")
                files.append((path,name))
            elif path.is_file():
                files.append((path,name))
            elif not path.is_dir():
                raise ValueError("Unsupported source object: "+str(path))
    for rel in INCLUDED_FILES:
        file=storage/rel.removeprefix("storage/") if rel.startswith("storage/") else root/rel
        if file.is_symlink() or file.resolve()!=file:
            raise ValueError("Symlink source blocked: "+rel)
        if file.is_file():
            files.append((file,rel))
    return files

def write_payload(root,tar_path,storage):
    manifest=[]
    seen={}
    with tarfile.open(tar_path,"w",format=tarfile.PAX_FORMAT) as tar:
        for path,relative in enumerate_files(root,storage):
            validate_rel(relative)
            before=path.lstat()
            info=tar.gettarinfo(str(path),arcname=relative)
            info.uid=10001 if relative.startswith("storage/app/") else 0
            info.gid=info.uid;info.uname="";info.gname=""
            info.mode=0o600 if relative.startswith((".env","storage/infrastructure/caddy/","storage/system/state/")) else (before.st_mode&0o777)
            symlink_target=None
            if stat.S_ISLNK(before.st_mode):
                symlink_target=safe_model_symlink(relative,os.readlink(path))
                raw=symlink_target.encode("utf8")
                sha=hashlib.sha256(raw).hexdigest()
                info.type=tarfile.SYMTYPE
                info.linkname=symlink_target
                info.size=0
                tar.addfile(info)
                size=len(raw)
                hardlink_of=None
            elif stat.S_ISREG(before.st_mode):
                key=(before.st_dev,before.st_ino)
                if key in seen:
                    first,sha=seen[key]
                    info.type=tarfile.LNKTYPE
                    info.linkname=first
                    info.size=0
                    tar.addfile(info)
                else:
                    sha=digest(path)
                    with path.open("rb") as stream:tar.addfile(info,stream)
                    seen[key]=(relative,sha)
                size=before.st_size
                hardlink_of=seen[key][0] if seen[key][0]!=relative else None
            else:
                raise ValueError("Non-regular source in backup")
            after=path.lstat()
            if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(
                after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
                raise RuntimeError("File changed while snapshot was being created: "+relative)
            manifest.append({"path":relative,"bytes":size,"sha256":sha,
                             "hardlink_of":hardlink_of,"symlink_target":symlink_target})
    return manifest

def capture(root,destination,url,*,quiesced=False):
    if not quiesced:raise ValueError("Required: --ack-writers-stopped after stopping all writers")
    root=Path(root).resolve()
    destination=Path(destination).absolute()
    if destination.exists():raise FileExistsError("Backup destination already exists")
    storage=configured_storage_root(root)
    if destination.resolve().is_relative_to(root) or destination.resolve().is_relative_to(storage):raise ValueError("Backup must be on independent storage outside project")
    destination.parent.mkdir(parents=True,exist_ok=True)
    scratch=Path(tempfile.mkdtemp(prefix=".photosorter-backup-",dir=destination.parent))
    os.chmod(scratch,0o700)
    try:
        files=write_payload(root,scratch/"files.tar",storage)
        pg_run(["pg_dump","--format=custom","--no-owner","--no-acl",
                "--file",str(scratch/"database.dump")],url)
        manifest={"schema":SCHEMA_VERSION,
                  "db_name":pg_env(url)["PGDATABASE"],
                  "source_root":str(root),
                  "source_storage_root":str(storage),
                  "files":files,
                  "db_sha256":digest(scratch/"database.dump"),
                  "tar_sha256":digest(scratch/"files.tar"),
                  "note":"Writers must have been stopped for DB/files consistency"}
        (scratch/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf8")
        os.chmod(scratch/"manifest.json",0o600)
        verify(scratch)
        scratch.rename(destination)
        return {"path":str(destination),"files":len(files),"db_sha256":manifest["db_sha256"]}
    except Exception:
        shutil.rmtree(scratch)
        raise

def verify(archive):
    archive=Path(archive).resolve()
    manifest=json.loads((archive/"manifest.json").read_text(encoding="utf8"))
    if manifest.get("schema")!=SCHEMA_VERSION:raise ValueError("Unsupported backup schema version")
    if digest(archive/"database.dump")!=manifest["db_sha256"]:raise ValueError("PostgreSQL dump checksum mismatch")
    if digest(archive/"files.tar")!=manifest["tar_sha256"]:raise ValueError("Tar checksum mismatch")
    listed={}
    for item in manifest["files"]:
        validate_rel(item["path"])
        if item["path"] in listed:raise ValueError("Duplicate backup member")
        listed[item["path"]]=item
    for name in listed:
        if any(parent.as_posix() in listed for parent in PurePosixPath(name).parents):
            raise ValueError("Backup member has a non-directory ancestor")
    with tarfile.open(archive/"files.tar","r") as tar:
        entries=tar.getmembers()
        members={m.name:m for m in entries}
        if len(members)!=len(entries) or set(members)!=set(listed):
            raise ValueError("Archive file list mismatch")
        for name,item in listed.items():
            member=members[name]
            if not (member.isfile() or member.islnk() or member.issym()):
                raise ValueError("Unsafe tar member type")
            if member.issym():
                link=item.get("symlink_target")
                if link is None or link!=member.linkname:
                    raise ValueError("Invalid symlink in archive")
                safe_model_symlink(name,link)
                raw=link.encode("utf8")
                if len(raw)!=item["bytes"] or hashlib.sha256(raw).hexdigest()!=item["sha256"]:
                    raise ValueError("Symlink checksum mismatch")
                continue
            if item.get("symlink_target") is not None:
                raise ValueError("Unexpected regular file instead of model symlink")
            if member.islnk():
                link=item["hardlink_of"]
                if not link or member.linkname!=link or link not in listed or not members[link].isfile() or (name.startswith("storage/app/") != link.startswith("storage/app/")):
                    raise ValueError("Unsafe hardlink in backup")
                if item["sha256"]!=listed[link]["sha256"] or item["bytes"]!=listed[link]["bytes"]:
                    raise ValueError("Hardlink metadata mismatch")
            stream=tar.extractfile(member)
            if stream is None:raise ValueError("Unreadable tar item")
            h=hashlib.sha256()
            size=0
            for chunk in iter(lambda:stream.read(BLOCK),b""):
                size+=len(chunk);h.update(chunk)
            if size!=item["bytes"] or h.hexdigest()!=item["sha256"]:
                raise ValueError("Corrupt backup member: "+name)
    return {"verified":True,"files":len(listed),"db_sha256":manifest["db_sha256"]}

def restore_test(archive,destination,url,*,confirmed=False):
    """Restore into an *empty* labelled staging path and a separate empty test DB."""
    if not confirmed:raise ValueError("Required: --confirm-staging")
    archive=Path(archive).resolve()
    destination=Path(destination).absolute()
    db=pg_env(url)["PGDATABASE"]
    manifest=json.loads((archive/"manifest.json").read_text(encoding="utf8"))
    if not db.startswith("sorter_restore_") or db==manifest.get("db_name"):
        raise ValueError("Restore DB name MUST start with sorter_restore_ and differ from source")
    if destination.exists():raise FileExistsError("Restore destination must not exist")
    if destination.resolve()==Path(manifest["source_root"]).resolve() or destination.is_relative_to(
        Path(manifest["source_root"]).resolve()):
        raise ValueError("Never restore inside source tree")
    source_storage=Path(manifest["source_storage_root"])
    if destination.resolve().is_relative_to(source_storage):
        raise ValueError("Never restore inside source storage")
    marker=destination.parent/".photosorter-staging-only"
    if not marker.is_file() or marker.read_text(encoding="utf8").strip()!="STAGING_ONLY":
        raise ValueError("Missing STAGING_ONLY marker in restore parent")
    verify(archive)
    rows=pg_run(["psql","-X","-A","-t","-c",
            "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"],url,capture=True)
    if rows.stdout.strip()!=b"0":raise ValueError("Restore target database must contain no user tables")
    # No extraction through tarfile.extractall: reject traversal and symlink entries.
    destination.mkdir(mode=0o700)
    for folder in INCLUDED_DIRS:
        (destination/folder).mkdir(parents=True,exist_ok=True)
    try:
        with tarfile.open(archive/"files.tar","r") as tar:
            for member in tar:
                rel=validate_rel(member.name)
                dest=destination.joinpath(*rel.parts)
                dest.parent.mkdir(parents=True,exist_ok=True)
                if member.isfile():
                    with tar.extractfile(member) as src,dest.open("xb") as dst:
                        shutil.copyfileobj(src,dst,BLOCK)
                    os.chmod(dest,member.mode&0o777)
                elif member.islnk():
                    linked=validate_rel(member.linkname)
                    origin=destination.joinpath(*linked.parts)
                    if not origin.is_file():raise ValueError("Invalid hardlink order")
                    os.link(origin,dest,follow_symlinks=False)
                elif member.issym():
                    safe_model_symlink(member.name,member.linkname)
                    os.symlink(member.linkname,dest)
                else:raise ValueError("Unsupported archive item")
        if os.geteuid()==0:
            # Preserve app UID/GID on a root staging restore, without exposing
            # Caddy private keys or host configuration to that UID.
            app=destination/"storage/app"
            for directory,dirs,files in os.walk(app,followlinks=False):
                os.chown(directory,10001,10001)
                os.chmod(directory,0o750)
                for name in dirs+files:os.chown(Path(directory)/name,10001,10001,follow_symlinks=False)
        pg_run(["pg_restore","--exit-on-error","--no-owner","--no-acl",
                "--dbname",db,str(archive/"database.dump")],url)
        for item in manifest["files"]:
            path=destination/item["path"]
            if item.get("symlink_target") is not None:
                target=os.readlink(path)
                safe_model_symlink(item["path"],target)
                if not any(path.resolve(strict=True).is_relative_to(destination/prefix) for prefix in MODEL_DIRS):
                    raise ValueError("Model symlink escaped restored model/cache roots")
                actual=hashlib.sha256(target.encode("utf8")).hexdigest()
            else:
                actual=digest(path)
            if actual!=item["sha256"]:raise ValueError("Restore checksum failure: "+item["path"])
        return {"restored":True,"db_name":db,"files":len(manifest["files"])}
    except Exception:
        # Leave the isolated target for inspection; NEVER touch the source/production.
        raise

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="operation",required=True)
    snap=sub.add_parser("capture")
    snap.add_argument("--root",required=True)
    snap.add_argument("--destination",required=True)
    snap.add_argument("--database-url",required=True)
    snap.add_argument("--ack-writers-stopped",action="store_true")
    check=sub.add_parser("verify")
    check.add_argument("--archive",required=True)
    restore=sub.add_parser("restore-test")
    restore.add_argument("--archive",required=True)
    restore.add_argument("--destination",required=True)
    restore.add_argument("--database-url",required=True)
    restore.add_argument("--confirm-staging",action="store_true")
    args=parser.parse_args(argv)
    if args.operation=="capture":result=capture(args.root,args.destination,args.database_url,quiesced=args.ack_writers_stopped)
    elif args.operation=="verify":result=verify(args.archive)
    else:result=restore_test(args.archive,args.destination,args.database_url,confirmed=args.confirm_staging)
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
