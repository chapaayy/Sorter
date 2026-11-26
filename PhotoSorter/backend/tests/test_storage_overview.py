from server.services.storage_overview import disk_overview

def fixtures():
    cap={"device":1,"total_bytes":1000,"used_bytes":700,"available_bytes":250,"sampled_at":"now"}
    tree={"device":"1","finished_at":"earlier","partial":False,"stale":False,"directory_bytes":20,
          "allocated_bytes":200,"comparable":True,"absolute_discrepancy_bytes":9,"unexplained_bytes":9}
    host={"at":"host","stale":False,"partial":False,"devices":{"1":{"allocated_bytes":100}},"tree_check":tree}
    registry={"sampled_at":"registry","reconciled_at":"earlier","stale":False,"errors":0,
              "devices":{"1":{"allocated_bytes":150}}}
    return cap,host,registry

def test_live_totals_and_separate_discrepancy():
    cap,host,registry=fixtures()
    result=disk_overview(cap,host,registry)
    assert (result["map_bytes"],result["system_bytes"],result["free_bytes"])==(279,421,300)
    assert result["adjustment_bytes"]==9 and result["sampled_at"]=="now"
    registry["devices"]["1"]["allocated_bytes"]+=50
    cap["used_bytes"]+=50
    assert disk_overview(cap,host,registry)["map_bytes"]==329
    assert disk_overview(cap,host,registry)["system_bytes"]==421

def test_no_dependency_on_full_check_and_no_fake_values():
    cap,host,registry=fixtures()
    host["tree_check"]={"partial":True}
    registry.update(partial=True,pending_changes=4)
    result=disk_overview(cap,host,registry)
    assert result["map_bytes"]==250 and result["directory_bytes"] is None and result["preliminary"]
    for update in ({"stale":True},{"partial":True},{"devices":{"2":{"allocated_bytes":100}}}):
        cap,host,registry=fixtures()
        host.update(update)
        assert disk_overview(cap,host,registry)["map_bytes"] is None

def test_keeps_last_directory_and_residual_during_incomplete_check():
    cap,host,registry=fixtures()
    host.update(directory_sample=host["tree_check"],discrepancy_sample=host["tree_check"],tree_check={"partial":True})
    assert disk_overview(cap,host,registry)["map_bytes"]==279
    cap["used_bytes"]=100
    assert disk_overview(cap,host,registry)["map_bytes"] is None
def test_root_details_use_own_sample_and_leave_unclassified_remainder():
    cap,host,registry=fixtures()
    host["disk_check"]={"device":"1","finished_at":"earlier","stale":False,"partial":False,"comparable":True,
        "capacity_after":{"total_bytes":1000,"used_bytes":500,"available_bytes":450},
        "map_storage":{"file_bytes":90,"directory_bytes":10},"docker_engine":{"file_bytes":200,"directory_bytes":20}}
    result=disk_overview(cap,host,registry)
    detail=result["system_details"]
    assert detail["system_bytes"]==400 and detail["remaining_bytes"]==180
    assert detail["categories"]["system_logs"] is None
    host["disk_check"]["device"]="2"
    assert disk_overview(cap,host,registry)["system_details"] is None

def test_partial_root_details_do_not_claim_a_residual():
    cap,host,registry=fixtures()
    host["disk_check"]={"device":"1","finished_at":"earlier","stale":False,"partial":True,"comparable":False,
        "capacity_after":{"total_bytes":1000,"used_bytes":500,"available_bytes":450},
        "map_storage":{"file_bytes":90,"directory_bytes":10},"docker_engine":{"file_bytes":200,"directory_bytes":20}}
    detail=disk_overview(cap,host,registry)["system_details"]
    assert detail["partial"] and detail["categories"]["docker_engine"]==220
    assert detail["system_bytes"] is None and detail["remaining_bytes"] is None

def test_cross_scope_hardlink_conflict_is_not_double_counted():
    cap,host,registry=fixtures()
    host["tree_check"]["cross_scope_links"]=1
    assert disk_overview(cap,host,registry)["map_bytes"] is None
