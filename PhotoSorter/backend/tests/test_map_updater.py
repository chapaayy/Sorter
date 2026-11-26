"""Safety regressions without contacting the real Docker daemon or VPS."""
import fcntl
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.services import update_gate
from server.api.routes import updater as api
from fastapi import HTTPException

MAINTENANCE=Path(__file__).resolve().parents[2]/"tools"/"maintenance"
sys.path.insert(0,str(MAINTENANCE))
import map_updater as host
import map_build
sys.path.remove(str(MAINTENANCE))


def test_gate_preserves_active_shared_lease_and_rejects_new_work(tmp_path,monkeypatch):
    monkeypatch.setattr(update_gate,"CONTROL",tmp_path)
    path=tmp_path/"activity.lock"
    path.touch()
    marker=tmp_path/"maintenance"
    with path.open("rb") as root:
        with update_gate.activity() as allowed:
            assert allowed
            marker.touch()
            with pytest.raises(BlockingIOError):
                fcntl.flock(root,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with update_gate.activity() as other:
                assert not other
        fcntl.flock(root,fcntl.LOCK_EX|fcntl.LOCK_NB)
        marker.unlink()
        with update_gate.activity() as blocked:
            assert not blocked
        fcntl.flock(root,fcntl.LOCK_UN)
    with update_gate.activity() as allowed:
        assert allowed


def test_non_owner_cannot_reach_host_socket(monkeypatch):
    def blocked(*args):
        raise AssertionError("A viewer must not open the socket")
    monkeypatch.setattr(api.socket,"socket",blocked)
    request=SimpleNamespace(state=SimpleNamespace(user={"username":"viewer","access_role":"viewer"}))
    for command in ("status","check","update","storage-cache","storage-logs","storage-check"):
        with pytest.raises(HTTPException) as error:
            api.request_host(request,command)
        assert error.value.status_code==403


def test_builder_is_removed_even_if_build_fails(tmp_path,monkeypatch):
    monkeypatch.setattr(map_build,"STATE",tmp_path/"builders")
    calls=[]
    def fake(args,cwd=None,timeout=0):
        calls.append(args)
        if args[:3]==["docker","buildx","build"]:
            raise subprocess.CalledProcessError(1,args)
    monkeypatch.setattr(map_build,"run",fake)
    with pytest.raises(subprocess.CalledProcessError):
        map_build.build(tmp_path,"a"*40,map_build.CURRENT)
    assert [c[2] for c in calls]==["create","build","rm"]
    name=calls[0][calls[0].index("--name")+1]
    assert calls[-1]==["docker","buildx","rm",name]
    assert not list(map_build.STATE.iterdir())
    assert not any("prune" in c for c in calls)


def test_cleanup_only_owned_old_unused_images(monkeypatch):
    new,previous,old,foreign,used=[x*40 for x in "abcde"]
    tags=["map-local/app:rev-"+x for x in (new,previous,old,foreign,used)]
    tags.append("different-project:latest")
    calls=[]
    def fake(*args,**kwargs):
        calls.append(args)
        if args[:2]==("image","ls"):
            return "\n".join(tags)
        if args[:2]==("ps","-aq"):
            return "active-container" if args[-1].endswith(used) else ""
        if args[:2]==("image","rm"):
            return ""
        raise AssertionError(args)
    def info(tag):
        revision=tag.rsplit("rev-",1)[-1]
        return {"Id":"sha256:"+revision,"Config":{"Labels":{
            "io.map.project":"other" if revision==foreign else host.PROJECT,
            "org.opencontainers.image.revision":revision}}}
    monkeypatch.setattr(host,"docker",fake)
    monkeypatch.setattr(host,"image_info",info)
    assert host.clean_images(new,previous)==[]
    assert [c for c in calls if c[:2]==("image","rm")]==[("image","rm","map-local/app:rev-"+old)]


def test_unknown_socket_operation_and_duplicate_update_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(host,"STATE",tmp_path/"status.json")
    monkeypatch.setattr(host,"MARKER",tmp_path/"maintenance")
    monkeypatch.setattr(host,"installed",lambda:("a"*40,"sha256:"+"a"*64))
    updater=host.Updater(tmp_path)
    assert updater.dispatch("shell")["rejected"]
    assert updater.dispatch("update")["rejected"]
    updater.publish(busy=True)
    assert updater.dispatch("check")["rejected"]
    assert updater.dispatch("update")["rejected"]
    assert updater.dispatch("storage-cache")["rejected"]
    assert updater.dispatch("storage-logs")["rejected"]
    updater.publish(busy=False)
    host.MARKER.touch()
    assert updater.dispatch("check")["rejected"]
