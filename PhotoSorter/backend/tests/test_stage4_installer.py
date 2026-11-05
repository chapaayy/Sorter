"""install.sh upgrade preflight with mocked docker: no real containers/volumes."""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]

@pytest.fixture
def deploy(tmp_path):
    root=tmp_path/"isolated"
    root.mkdir()
    shutil.copy2(ROOT/"install.sh",root/"install.sh")
    (root/".env").write_text("DOMAIN=stage4.example.test\n",encoding="utf8")
    (root/".env.example").write_text("DOMAIN=sorter.example.com\n",encoding="utf8")
    (root/"compose.yaml").write_text("name: outdoor-sorter\n",encoding="utf8")
    (root/".env.generated").write_text("POSTGRES_PASSWORD=synthetic_test_password_000\nADMIN_PASSWORD=synthetic_test_admin_password_111\n",encoding="utf8")
    stub=tmp_path/"stubs"
    stub.mkdir()
    docker=stub/"docker"
    docker.write_text("""#!/bin/sh
echo "$*" >> "$STAGE4_DOCKER_LOG"
if [ "$1" = volume ] && [ "$2" = inspect ]; then
  [ "$STAGE4_VOLUME" = 1 ] && exit 0 || exit 1
fi
exit 0
""",encoding="utf8")
    docker.chmod(0o755)
    env=os.environ.copy()
    env.update({"PATH":str(stub)+":"+env["PATH"],
        "STAGE4_DOCKER_LOG":str(tmp_path/"docker.log"),
        "STAGE4_VOLUME":"1",
        "PHOTOSORTER_WORKER_CPUSET":str(min(os.sched_getaffinity(0)))})
    def run(*args,overrides=None):
        e={**env,**(overrides or {})}
        return subprocess.run(["bash",str(root/"install.sh"),*args],cwd=root,env=e,
            text=True,capture_output=True,timeout=15)
    return root,run,tmp_path/"docker.log"

def test_check_does_not_mutate_secrets_or_launch_containers(deploy):
    root,run,log=deploy
    before=(root/".env.generated").read_bytes()
    result=run("--check")
    assert result.returncode==0,result.stderr
    assert (root/".env.generated").read_bytes()==before
    calls=log.read_text()
    assert "compose config --quiet" in calls
    assert "compose up" not in calls
    assert "Initial password" not in result.stdout

def test_upgrade_blocks_missing_original_secrets(deploy):
    root,run,log=deploy
    (root/".env.generated").unlink()
    result=run("--deploy")
    assert result.returncode!=0
    assert "ORIGINAL credentials" in result.stderr
    assert not (root/".env.generated").exists()
    assert "compose up" not in log.read_text()

def test_upgrade_requires_explicit_backup_ack(deploy):
    root,run,log=deploy
    before=(root/".env.generated").read_bytes()
    assert run("--deploy").returncode!=0
    assert "compose up" not in log.read_text()
    yes=run("--deploy",overrides={"PHOTOSORTER_APPROVE_UPGRADE":"VERIFIED_BACKUP_AND_ROLLBACK"})
    assert yes.returncode==0,yes.stderr
    assert "compose up -d --build" in log.read_text()
    assert (root/".env.generated").read_bytes()==before
    assert "password" not in yes.stdout.lower()

def test_invalid_cpu_preflight_fails_without_up(deploy):
    root,run,log=deploy
    result=run("--check",overrides={"PHOTOSORTER_WORKER_CPUSET":"999999"})
    assert result.returncode!=0
    assert "CPU affinity" in result.stderr
    assert "compose up" not in log.read_text()
