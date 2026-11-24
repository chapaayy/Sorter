"""Stage-one target contract checks; not runtime path or lifecycle tests."""
import json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "storage-layout-v2.json"

def test_storage_v2_target_contract():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["layout_version"] == 2
    assert data["status"] == "target_contract_not_active"
    assert data["container_app_root"] == "/storage/app"
    assert data["quotas_enabled_default"] is False
    assert data["archive_ttl_seconds"] == 3600
    assert data["archive_sweep_seconds"] == 30
    assert sum(data["log_budgets_mib"].values()) == 1132
    rows = data["categories"]
    by_id = {r["id"]: r for r in rows}
    assert len(rows) == len(by_id)
    required = set("fo_original fo_normalized result_media result_metadata run_state fo_thumbnail reference_object reference_gallery reference_thumbnail reference_embedding fo_upload_part reference_upload_part transcode_temp video_frames processing_staging fo_embedding_temp zip_results zip_construction zip_references zip_fragment archive_lock atomic_fragment model_download model_weights model_source model_metadata technical_cache scratch postgres_data caddy_state service_log run_log access_log audit_snapshot audit_event updater_backup updater_workspace builder_marker runtime_image build_cache system_runtime tmpfs unknown".split())
    assert required <= by_id.keys()
    for row in rows:
        for field in ("id", "scope", "path", "owner", "producer", "publication", "cleanup", "recovery", "coordination", "accounting", "verification", "growth", "consumer"):
            assert isinstance(row[field], str) and row[field].strip()
        assert not row["path"].startswith("/")
        assert ".." not in row["path"].split("/")
        assert 2 <= row["stage"] <= 7
    for name in ("fo_original", "fo_normalized", "result_media", "fo_thumbnail"):
        assert by_id[name]["scope"] == "personal"
    for name in ("zip_results", "zip_construction", "zip_references", "transcode_temp", "fo_upload_part"):
        assert by_id[name]["scope"] == "temporary"
        assert by_id[name]["path"].startswith("app/temporary/")
    assert by_id["reference_embedding"]["scope"] == "shared"
    assert by_id["unknown"]["cleanup"] == "never automatic deletion"
