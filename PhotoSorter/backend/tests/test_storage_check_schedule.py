"""Exercise the real queue without Docker or systemd."""
import sys
from pathlib import Path
from datetime import datetime,timezone,timedelta

MAINTENANCE=Path(__file__).resolve().parents[2]/"tools"/"maintenance"
sys.path.insert(0,str(MAINTENANCE))
import host_logs as host
import map_updater  # resolve the real atomic writer before restoring sys.path
sys.path.remove(str(MAINTENANCE))

def setup(tmp_path):
    control=tmp_path/"system/updater/control"
    control.mkdir(parents=True)
    (control.parent/"private").mkdir()
    return control

def now():return datetime.now(timezone.utc).isoformat()

def test_queue_deduplication_readiness_and_cooldown(tmp_path):
    control=setup(tmp_path)
    request=host.request_check(tmp_path)
    assert request["state"]=="queued"
    assert host.request_check(tmp_path)["rejected"]
    assert host._claim_check(control,{},ready=False) is None
    (control/"maintenance").touch()
    assert host._claim_check(control,{}) is None
    (control/"maintenance").unlink()
    claim=host._claim_check(control,{})
    assert claim["request_id"]==request["request_id"] and claim["state"]=="running"
    assert host.request_check(tmp_path)["rejected"]
    host._finish_check(control,claim,{"comparable":True,"finished_at":now()})
    assert host._check_state(control)["state"]=="completed"
    assert host.request_check(tmp_path)["rejected"]
    assert host._claim_check(control,{"comparable":True,"finished_at":now()}) is None

def test_deployment_request_survives_running_check_and_retry(tmp_path):
    control=setup(tmp_path)
    claim=host._claim_check(control,{})
    newer=host.request_check(tmp_path,automatic=True)
    host._finish_check(control,claim,{"comparable":True,"finished_at":now()})
    assert host._check_state(control)["request_id"]==newer["request_id"]
    claim=host._claim_check(control,{"comparable":True,"finished_at":now()})
    assert claim["reason"]=="deployment"
    host._finish_check(control,claim,{"comparable":False,"finished_at":now()})
    assert host._check_state(control)["state"]=="retry"
    assert host._claim_check(control,{}) is None
    state=host._check_state(control)
    state["finished_at"]=(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()
    host._write_check(control,state)
    retry=host._claim_check(control,{})
    assert retry["request_id"]==newer["request_id"]

def test_baseline_survives_incomplete_attempt():
    good={"device":"1","finished_at":now(),"partial":False,"comparable":True,
          "directory_bytes":4096,"unexplained_bytes":-512,"absolute_discrepancy_bytes":512}
    directories,adjustment=host._baseline({"tree_check":good},{"partial":True})
    assert directories["directory_bytes"]==4096 and adjustment["unexplained_bytes"]==-512
    assert host._baseline({"directory_sample":directories,"discrepancy_sample":adjustment},{"partial":True})==(directories,adjustment)
