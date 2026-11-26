from server.services.storage_overview import disk_overview

def fixtures():
    cap={"device":1,"total_bytes":1000,"used_bytes":700,"available_bytes":250}
    tree={"device":"1","finished_at":"sample","partial":False,"stale":False,
          "allocated_bytes":200,"capacity_after":{"total_bytes":1000,"used_bytes":600,"available_bytes":350},
          "comparable":True,"absolute_discrepancy_bytes":9}
    return cap,{"stale":False,"tree_check":tree}

def test_paired_capacity_and_independent_map_not_registry():
    cap,host=fixtures()
    result=disk_overview(cap,host)
    assert (result["map_bytes"],result["system_bytes"],result["free_bytes"])==(200,400,400)
    assert result["used_bytes"]==600 and result["available_bytes"]==350
    assert host["tree_check"]["absolute_discrepancy_bytes"]==9

def test_no_guess_on_stale_partial_wrong_device_or_missing_capacity():
    for update in ({"stale":True},{"partial":True},{"device":"2"},{"capacity_after":None},{"allocated_bytes":601}):
        cap,host=fixtures()
        host["tree_check"].update(update)
        result=disk_overview(cap,host)
        assert result["map_bytes"] is None and result["system_bytes"] is None
        assert result["used_bytes"]==700 and result["free_bytes"]==300

def test_root_details_use_own_sample_and_leave_unclassified_remainder():
    cap,host=fixtures()
    host["disk_check"]={"device":"1","finished_at":"earlier","stale":False,"partial":False,"comparable":True,
        "capacity_after":{"total_bytes":1000,"used_bytes":500,"available_bytes":450},
        "map_storage":{"file_bytes":90,"directory_bytes":10},"docker_engine":{"file_bytes":200,"directory_bytes":20}}
    result=disk_overview(cap,host)
    detail=result["system_details"]
    assert detail["system_bytes"]==400 and detail["remaining_bytes"]==180
    assert detail["categories"]["system_logs"] is None
    host["disk_check"]["device"]="2"
    assert disk_overview(cap,host)["system_details"] is None

def test_partial_root_details_do_not_claim_a_residual():
    cap,host=fixtures()
    host["disk_check"]={"device":"1","finished_at":"earlier","stale":False,"partial":True,"comparable":False,
        "capacity_after":{"total_bytes":1000,"used_bytes":500,"available_bytes":450},
        "map_storage":{"file_bytes":90,"directory_bytes":10},"docker_engine":{"file_bytes":200,"directory_bytes":20}}
    detail=disk_overview(cap,host)["system_details"]
    assert detail["partial"] and detail["categories"]["docker_engine"]==220
    assert detail["system_bytes"] is None and detail["remaining_bytes"] is None
