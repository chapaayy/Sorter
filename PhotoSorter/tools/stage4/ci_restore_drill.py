"""CI-only real pg_dump/pg_restore trial. Does NOT connect to any production DB."""
from __future__ import annotations
import hashlib
import os
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
import psycopg
from psycopg import sql
from snapshot import capture,verify,restore_test

def main():
    if os.environ.get("GITHUB_ACTIONS")!="true":
        raise RuntimeError("This fixture is deliberately CI-only; use snapshot.py on a staging host")
    source=os.environ["DATABASE_URL"]
    parsed=urlsplit(source)
    if parsed.hostname not in ("127.0.0.1","localhost") or parsed.path!="/sorter_test":
        raise RuntimeError("Refusing non-local or non-disposable DB")
    target_name="sorter_restore_"+uuid.uuid4().hex[:12]
    admin=urlunsplit((parsed.scheme,parsed.netloc,"/postgres",parsed.query,parsed.fragment))
    target=urlunsplit((parsed.scheme,parsed.netloc,"/"+target_name,parsed.query,parsed.fragment))
    token=uuid.uuid4().hex
    data=b"synthetic-reference-and-FO"
    signature=hashlib.sha256(data).hexdigest()
    with psycopg.connect(admin,autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_name)))
    try:
        with psycopg.connect(source) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS stage4_restore_marker (key text PRIMARY KEY, digest text NOT NULL)")
            conn.execute("INSERT INTO stage4_restore_marker(key,digest) VALUES (%s,%s)",(token,signature))
        with tempfile.TemporaryDirectory(prefix="photosorter-ci-stage4-") as scratch:
            temp=Path(scratch)
            root=temp/"original"
            a=root/"PhotoSorter"/"data"/"uploads"/"fake-batch"
            b=root/"PhotoSorter"/"data"/"references"/"SAM-0001"
            a.mkdir(parents=True);b.mkdir(parents=True)
            (root/"Models"/"models"/"megaloc").mkdir(parents=True)
            (root/".env.generated").write_text("POSTGRES_PASSWORD=test_only_no_real_data\nADMIN_PASSWORD=test_only_no_real_data\n")
            (root/".env").write_text("DOMAIN=stage4.example.test\n")
            (root/"compose.yaml").write_text("name: staging-only\n")
            original=a/"fo.jpg"
            original.write_bytes(data)
            os.link(original,b/"ref.jpg")
            archive=temp/"backup"
            result=capture(root,archive,source,quiesced=True)
            assert verify(archive)["verified"] and result["files"]>=4
            (temp/".photosorter-staging-only").write_text("STAGING_ONLY")
            restored=temp/"restored"
            restore_test(archive,restored,target,confirmed=True)
            result_a=restored/original.relative_to(root)
            result_b=restored/(b/"ref.jpg").relative_to(root)
            assert result_a.read_bytes()==data and result_b.read_bytes()==data
            assert result_a.stat().st_ino==result_b.stat().st_ino
            with psycopg.connect(target) as conn:
                row=conn.execute("SELECT digest FROM stage4_restore_marker WHERE key=%s",(token,)).fetchone()
                assert row and row[0]==signature
            print("STAGE4_DISPOSABLE_RESTORE_OK",target_name,result["files"],signature)
    finally:
        with psycopg.connect(admin,autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(target_name)))

if __name__=="__main__":main()
