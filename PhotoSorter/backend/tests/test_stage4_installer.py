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
    host=root/"PhotoSorter/tools/maintenance/setup_tcp_bbr.sh"
    host.parent.mkdir(parents=True)
    shutil.copy2(ROOT/"PhotoSorter/tools/maintenance/setup_tcp_bbr.sh",host)
    (root/".env").write_text("DOMAIN=stage4.example.test\n",encoding="utf8")
    (root/".env.example").write_text("DOMAIN=sorter.example.com\n",encoding="utf8")
    (root/"compose.yaml").write_text("name: outdoor-sorter\n",encoding="utf8")
    (root/".env.generated").write_text("POSTGRES_PASSWORD=synthetic_test_password_000\nADMIN_PASSWORD=synthetic_test_admin_password_111\n",encoding="utf8")
    stub=tmp_path/"stubs"
    stub.mkdir()
    docker=stub/"docker"
    docker.write_text("""#!/bin/sh
echo "$*" >> "$STAGE4_DOCKER_LOG"
if [ "$1" = compose ]; then echo "$PHOTOSORTER_CADDY_TCP_CC" >> "$STAGE4_CADDY_TCP_CC_LOG"; fi
if [ "$1" = volume ] && [ "$2" = inspect ]; then
  [ "$STAGE4_VOLUME" = 1 ] && exit 0 || exit 1
fi
exit 0
""",encoding="utf8")
    docker.chmod(0o755)
    (stub/"id").write_text('#!/bin/sh\nif [ "$1" = "-u" ]; then echo 0; else /usr/bin/id "$@"; fi\n')
    (stub/"id").chmod(0o755)
    (stub/"modprobe").write_text('#!/bin/sh\n[ "$STAGE4_BBR_MODULE" = "missing" ] && exit 1\necho bbr > "$STAGE4_BBR_LOADED"\n')
    (stub/"modprobe").chmod(0o755)
    (stub/"sysctl").write_text("""#!/bin/sh
case "$1 $2" in
  "-n net.ipv4.tcp_available_congestion_control")
    if [ -f "$STAGE4_BBR_LOADED" ]; then echo "reno cubic bbr"; else echo "reno cubic"; fi ;;
  "-n net.ipv4.tcp_congestion_control")
    if [ -f "$STAGE4_BBR_ACTIVE" ]; then cat "$STAGE4_BBR_ACTIVE"; else echo cubic; fi ;;
  "-w net.ipv4.tcp_congestion_control=bbr")
    echo bbr > "$STAGE4_BBR_ACTIVE"; echo "net.ipv4.tcp_congestion_control = bbr" ;;
  "-w net.ipv4.tcp_congestion_control=cubic")
    echo cubic > "$STAGE4_BBR_ACTIVE"; echo "net.ipv4.tcp_congestion_control = cubic" ;;
  *) exit 1 ;;
esac
""")
    (stub/"sysctl").chmod(0o755)
    env=os.environ.copy()
    env.update({"PATH":str(stub)+":"+env["PATH"],
        "STAGE4_DOCKER_LOG":str(tmp_path/"docker.log"),
        "STAGE4_CADDY_TCP_CC_LOG":str(tmp_path/"caddy-tcp.log"),
        "STAGE4_VOLUME":"1",
        "STAGE4_BBR_MODULE":"ok",
        "STAGE4_BBR_LOADED":str(tmp_path/"loaded"),
        "STAGE4_BBR_ACTIVE":str(tmp_path/"active"),
        "PHOTOSORTER_BBR_ETC_ROOT":str(tmp_path/"mock-etc"),
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
    assert any(line.endswith("config --quiet") for line in calls.splitlines())
    assert "compose up" not in calls
    assert "Initial password" not in result.stdout

def test_upgrade_blocks_missing_original_secrets(deploy):
    root,run,log=deploy
    (root/".env.generated").unlink()
    result=run("--deploy")
    assert result.returncode!=0
    assert "ORIGINAL credentials" in result.stderr
    assert not (root/".env.generated").exists()
    assert not any(line.endswith("up -d --build") for line in log.read_text().splitlines())

def test_beta_upgrade_uses_one_command_without_approval_switches(deploy):
    root,run,log=deploy
    before=(root/".env.generated").read_bytes()
    result=run("--deploy")
    assert result.returncode==0,result.stderr
    assert any(line.endswith("up -d --build") for line in log.read_text().splitlines())
    assert (root/".env.generated").read_bytes()==before
    assert "password" not in result.stdout.lower()

def test_invalid_cpu_preflight_fails_without_up(deploy):
    root,run,log=deploy
    result=run("--check",overrides={"PHOTOSORTER_WORKER_CPUSET":"999999"})
    assert result.returncode!=0
    assert "CPU affinity" in result.stderr
    assert not any(line.endswith("up -d --build") for line in log.read_text().splitlines())


def test_check_does_not_load_bbr_or_write_host_settings(deploy):
    root,run,log=deploy
    result=run("--check")
    assert result.returncode==0,result.stderr
    assert not (root.parent/"mock-etc").exists()
    assert not (root.parent/"loaded").exists()
    assert "Host TCP congestion control: cubic" in result.stdout

def test_deploy_enables_bbr_without_touching_qdisc(deploy):
    root,run,log=deploy
    result=run("--deploy")
    assert result.returncode==0,result.stderr
    etc=root.parent/"mock-etc"
    assert (etc/"sysctl.d/99-photosorter-bbr.conf").read_text().strip()=="net.ipv4.tcp_congestion_control = bbr"
    assert (etc/"modules-load.d/99-photosorter-bbr.conf").read_text().strip()=="tcp_bbr"
    assert (root.parent/"active").read_text().strip()=="bbr"
    assert "BBR enabled" in result.stdout
    assert (root.parent/"caddy-tcp.log").read_text().splitlines()[-1]=="bbr"

def test_bbr_opt_out_does_not_touch_host(deploy):
    root,run,log=deploy
    result=run("--deploy",overrides={"PHOTOSORTER_ENABLE_BBR":"0"})
    assert result.returncode==0,result.stderr
    assert not (root.parent/"mock-etc").exists()
    assert not (root.parent/"loaded").exists()
    assert (root.parent/"caddy-tcp.log").read_text().splitlines()[-1]=="cubic"

def test_missing_bbr_module_warns_but_site_still_deploys(deploy):
    root,run,log=deploy
    result=run("--deploy",overrides={"STAGE4_BBR_MODULE":"missing"})
    assert result.returncode==0,result.stderr
    assert "module unavailable" in result.stderr
    assert (root.parent/"caddy-tcp.log").read_text().splitlines()[-1]=="cubic"
    assert not (root.parent/"mock-etc").exists()
    assert any(line.endswith("up -d --build") for line in log.read_text().splitlines())

def test_explicit_bbr_disable_only_removes_owned_files(deploy):
    root,run,log=deploy
    assert run("--deploy").returncode==0
    etc=root.parent/"mock-etc"
    other=etc/"sysctl.d/50-unrelated.conf"
    other.write_text("net.ipv4.ip_forward = 1\n")
    proc=subprocess.run(["bash",str(root/"PhotoSorter/tools/maintenance/setup_tcp_bbr.sh"),"--disable"],
        cwd=root,env={**os.environ,
            "PATH":str(root.parent/"stubs")+":"+os.environ["PATH"],
            "PHOTOSORTER_BBR_ETC_ROOT":str(etc),
            "STAGE4_BBR_ACTIVE":str(root.parent/"active"),
            "STAGE4_BBR_LOADED":str(root.parent/"loaded"),
            "STAGE4_BBR_MODULE":"ok"},text=True,capture_output=True)
    assert proc.returncode==0,proc.stderr
    assert other.exists()
    assert not (etc/"sysctl.d/99-photosorter-bbr.conf").exists()
    assert not (etc/"modules-load.d/99-photosorter-bbr.conf").exists()
    assert (root.parent/"active").read_text().strip()=="cubic"
