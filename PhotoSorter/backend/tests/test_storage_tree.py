"""Compare real filesystem evidence to GNU du, without Docker or a database."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess

ROOT=Path(__file__).resolve().parents[3]
SPEC=importlib.util.spec_from_file_location("storage_tree_test",ROOT/"PhotoSorter/tools/maintenance/storage_tree.py")
tree=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tree)

def test_tree_includes_directories_and_deduplicates_hardlinks(tmp_path):
    app=tmp_path/"app"
    app.mkdir()
    (app/"nested").mkdir()
    (app/"empty").mkdir()
    host=tmp_path/"system"
    host.mkdir()
    source=app/"data"
    with source.open("wb") as stream:
        stream.seek(1024**2)
        stream.write(b"x")
    os.link(source,app/"nested/link")
    (host/"metadata").write_bytes(b"abc")
    (app/"symlink").symlink_to("/etc")
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as endpoint:
        cwd=os.getcwd()
        try:
            os.chdir(host)
            endpoint.bind("control.sock")
        finally:os.chdir(cwd)
        report=tree.measure_tree(tmp_path)
        assert not report["partial"],report
        assert report["allocated_bytes"]==int(subprocess.check_output(["du","-x","-B1","-s",str(tmp_path)],text=True).split()[0])
        assert report["app"]["hardlink_paths"]==1
        assert report["directory_bytes"]==sum(p.stat().st_blocks*512 for p in (tmp_path,app,app/"nested",app/"empty",host))
        assert report["app"]["file_bytes"]==source.stat().st_blocks*512+(app/"symlink").lstat().st_blocks*512
    assert tree.measure_tree(tmp_path,limit=1)["partial"]
    os.link(source,host/"cross")
    os.link(source,host/"cross2")
    assert tree.measure_tree(tmp_path)["cross_scope_links"]==1
    assert tree.measure_tree(tmp_path)["partial"]
    # Multiple aliases in either scope must count as a single conflicting inode.
    another=app/"another"
    another.write_bytes(b"second inode")
    os.link(another,host/"second-cross")
    result=tree.measure_tree(tmp_path)
    assert result["cross_scope_links"]==2
    assert result["allocated_bytes"]==int(subprocess.check_output(["du","-x","-B1","-s",str(tmp_path)],text=True).split()[0])

def test_comparison_does_not_hide_unexplained_file(tmp_path):
    (tmp_path/"app").mkdir()
    (tmp_path/"system").mkdir()
    (tmp_path/"app"/"unseen").write_bytes(b"x"*4096)
    row={"allocated_bytes":0,"partial":False,"pending_changes":0,"reserved_bytes":0}
    host={"partial":False,"physical_fingerprint":"fixture-stable","devices":{str(tmp_path.stat().st_dev):{"allocated_bytes":0}}}
    report=tree.compare(tmp_path,lambda:host,sample=lambda:dict(row))
    assert report["comparable"]
    assert report["unexplained_bytes"]==(tmp_path/"app"/"unseen").stat().st_blocks*512
    assert report["absolute_discrepancy_bytes"]==report["unexplained_bytes"]
    host["devices"][str(tmp_path.stat().st_dev)]["allocated_bytes"]=report["unexplained_bytes"]
    cancelled=tree.compare(tmp_path,lambda:host,sample=lambda:dict(row))
    assert cancelled["unexplained_bytes"]==0 and cancelled["absolute_discrepancy_bytes"]>0
    host["devices"][str(tmp_path.stat().st_dev)]["allocated_bytes"]=0
    row["allocated_bytes"]=report["app"]["file_bytes"]
    assert tree.compare(tmp_path,lambda:host,sample=lambda:dict(row))["unexplained_bytes"]==0
    row["partial"]=True
    assert tree.compare(tmp_path,lambda:host,sample=lambda:dict(row))["unexplained_bytes"] is None


def test_infrastructure_growth_during_independent_walk_is_not_comparable(tmp_path):
    (tmp_path/"app").mkdir()
    system=tmp_path/"system"
    system.mkdir()
    log=system/"test.log"
    log.write_bytes(b"x"*4096)
    registry={"allocated_bytes":0,"partial":False,"pending_changes":0,"reserved_bytes":0}
    def host():
        st=log.stat()
        return {"partial":False,"physical_fingerprint":str(st.st_blocks),
                "devices":{str(st.st_dev):{"allocated_bytes":st.st_blocks*512}}}
    def scan(path):
        with log.open("ab") as stream:stream.write(b"x"*4096)
        return tree.measure_tree(path)
    changing=tree.compare(tmp_path,host,sample=lambda:registry,scan=scan)
    assert changing["host_delta_bytes"]>0
    assert not changing["host_stable"] and not changing["comparable"]
    assert changing["absolute_discrepancy_bytes"] is None
    stable=tree.compare(tmp_path,host,sample=lambda:registry)
    assert stable["comparable"] and stable["absolute_discrepancy_bytes"]==0
    # A real, repeatable undercount must still be reported without tolerance.
    def wrong():
        row=host()
        row["devices"][str(log.stat().st_dev)]["allocated_bytes"]-=4096
        return row
    mismatch=tree.compare(tmp_path,wrong,sample=lambda:registry)
    assert mismatch["comparable"] and mismatch["absolute_discrepancy_bytes"]==4096
