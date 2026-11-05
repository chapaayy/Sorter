"""Consistent, *operator-quiesced* PhotoSorter archive and safe disposable restore.

No Docker stop/start, schema migration, live deployment or destructive cleanup here.
Requires PostgreSQL pg_dump/pg_restore/psql clients matching the DB major version.
This archive is sensitive: it includes .env.generated and originals. Store offsite.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit,unquote

INCLUDED_DIRS=("PhotoSorter/data","Models/models")
INCLUDED_FILES=(".env",".env.generated","compose.yaml","PhotoSorter/docker/caddy/Caddyfile")
SCHEMA_VERSION=1
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
    # Never place plaintext DB URL/password in child process argv or log output.
    return subprocess.run(args,env=env,check=True,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                          stderr=subprocess.PIPE)

def validate_rel(name):
    posix=PurePosixPath(name)
    if not name or posix.is_absolute() or any(p in ("..",".") for p in posix.parts) or "\\" in name:
        raise ValueError("Unsafe backup member")
    if not (any(name==d or name.startswith(d+"/") for d in INCLUDED_DIRS)
            or name in INCLUDED_FILES):
        raise ValueError("Unexpected backup member: "+name)
    return posix

def enumerate_files(root):
    files=[]
    for rel in INCLUDED_DIRS:
        folder=root/rel
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("Missing or symlinked backup directory: "+rel)
        for p in sorted(folder.rglob("*")):
            if p.is_symlink():raise ValueError("Symlink not allowed in snapshot: "+str(p))
            if p.is_file():
                if not p.is_relative_to(folder):raise ValueError("Unsafe source")
                files.append(p)
            elif not p.is_dir():raise ValueError("Unsupported source object: "+str(p))
    for rel in INCLUDED_FILES:
        file=root/rel
        if file.is_symlink():raise ValueError("Symlink source blocked: "+rel)
        if file.is_file():files.append(file)
    if not (root/".env.generated").is_file():
        raise ValueError("Missing .env.generated: cannot preserve admin/DB credentials")
    return files

def write_payload(root,tar_path):
    manifest=[]
    seen={}
    with tarfile.open(tar_path,"w",format=tarfile.PAX_FORMAT) as tar:
        for path in enumerate_files(root):
            relative=path.relative_to(root).as_posix()
            validate_rel(relative)
            before=path.stat()
            if not stat.S_ISREG(before.st_mode):raise ValueError("Non-regular file in backup")
            key=(before.st_dev,before.st_ino)
            info=tar.gettarinfo(str(path),arcname=relative)
            info.uid=10001;info.gid=10001;info.uname="";info.gname=""
            info.mode=0o600 if relative.startswith(".env") else (before.st_mode&0o777)
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
            after=path.stat()
            if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(
                after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
                raise RuntimeError("File changed while snapshot was being created: "+relative)
            manifest.append({"path":relative,"bytes":before.st_size,"sha256":sha,
                             "hardlink_of":seen[key][0] if seen[key][0]!=relative else None})
    return manifest

def capture(root,destination,url,*,quiesced=False):
    if not quiesced:raise ValueError("Required: --ack-writers-stopped after stopping all writers")
    root=Path(root).resolve()
    destination=Path(destination).absolute()
    if destination.exists():raise FileExistsError("Backup destination already exists")
    if destination.is_relative_to(root):raise ValueError("Backup must be on independent storage outside project")
    destination.parent.mkdir(parents=True,exist_ok=True)
    scratch=Path(tempfile.mkdtemp(prefix=".photosorter-backup-",dir=destination.parent))
    os.chmod(scratch,0o700)
    try:
        files=write_payload(root,scratch/"files.tar")
        pg_run(["pg_dump","--format=custom","--no-owner","--no-acl",
                "--file",str(scratch/"database.dump")],url)
        manifest={"schema":SCHEMA_VERSION,
                  "db_name":pg_env(url)["PGDATABASE"],
                  "source_root":str(root),
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
    with tarfile.open(archive/"files.tar","r") as tar:
        members={m.name:m for m in tar.getmembers()}
        if set(members)!=set(listed):raise ValueError("Archive file list mismatch")
        for name,item in listed.items():
            member=members[name]
            if not (member.isfile() or member.islnk()):raise ValueError("Unsafe tar member type")
            if member.islnk():
                link=item["hardlink_of"]
                if not link or member.linkname!=link or link not in listed:
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
    marker=destination.parent/".photosorter-staging-only"
    if not marker.is_file() or marker.read_text(encoding="utf8").strip()!="STAGING_ONLY":
        raise ValueError("Missing STAGING_ONLY marker in restore parent")
    verify(archive)
    rows=pg_run(["psql","-X","-A","-t","-c",
            "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"],url,capture=True)
    if rows.stdout.strip()!=b"0":raise ValueError("Restore target database must contain no user tables")
    # No extraction through tarfile.extractall: reject traversal and symlink entries.
    destination.mkdir(mode=0o700)
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
                else:raise ValueError("Unsupported archive item")
        pg_run(["pg_restore","--exit-on-error","--no-owner","--no-acl",
                "--dbname",db,str(archive/"database.dump")],url)
        for item in manifest["files"]:
            path=destination/item["path"]
            if digest(path)!=item["sha256"]:raise ValueError("Restore checksum failure: "+item["path"])
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
