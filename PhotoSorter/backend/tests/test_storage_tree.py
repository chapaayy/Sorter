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
    assert tree.measure_tree(tmp_path)["cross_scope_links"]==1
    assert tree.measure_tree(tmp_path)["partial"]

def test_comparison_does_not_hide_unexplained_file(tmp_path):
    (tmp_path/"app").mkdir()
    (tmp_path/"system").mkdir()
    (tmp_path/"app"/"unseen").write_bytes(b"x"*4096)
    row={"allocated_bytes":0,"partial":False,"pending_changes":0,"reserved_bytes":0}
    host={"partial":False,"devices":{str(tmp_path.stat().st_dev):{"allocated_bytes":0}}}
    report=tree.compare(tmp_path,host,sample=lambda:dict(row))
    assert report["comparable"]
    assert report["unexplained_bytes"]==(tmp_path/"app"/"unseen").stat().st_blocks*512
    row["allocated_bytes"]=report["app"]["file_bytes"]
    assert tree.compare(tmp_path,host,sample=lambda:dict(row))["unexplained_bytes"]==0
    row["partial"]=True
    assert tree.compare(tmp_path,host,sample=lambda:dict(row))["unexplained_bytes"] is None
