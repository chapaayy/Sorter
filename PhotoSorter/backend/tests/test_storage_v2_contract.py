"""Stage-one target contract checks; not runtime path or lifecycle tests."""
import json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "storage-layout-v2.json"

def test_storage_v2_target_contract():
    data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert data["layout_version"] == 2
    assert data["status"] == "foundation_active_lifecycle_pending"
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


def test_stage_one_site_review_coverage():
    import re
    from collections import Counter
    docs = CONTRACT.parent
    def rows(path, pattern):
        current = None
        result = []
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.startswith('## `'):
                current = line.split('`')[1]
            match = re.match(pattern, line)
            if match:
                assert current
                result.append((current, int(match[1])))
        return result
    candidates = []
    for path in sorted(docs.glob('STORAGE_V2_SOURCE_SITES_*.md')):
        candidates.extend(rows(path, r'- L(\d+):'))
    review = docs / 'STORAGE_V2_SITE_DISPOSITIONS.md'
    dispositions = rows(review, r'\| (\d+) \|')
    assert len(candidates) == len(set(candidates)) == 573
    assert Counter(dispositions) == Counter(candidates)
    ids = {c['id'] for c in json.loads(CONTRACT.read_text())['categories']}
    for line in review.read_text(encoding='utf-8').splitlines():
        if re.match(r'\| \d+ \|', line):
            cells = line.split('|')
            assert set(c.strip() for c in cells[3].split(',')) <= ids
            assert cells[2].strip() and cells[4].strip()
    backlog = (docs / 'STORAGE_V2_REVIEW_BACKLOG.md').read_text(encoding='utf-8')
    modules = (docs / 'STORAGE_V2_MODULE_REVIEW.md').read_text(encoding='utf-8')
    expected = re.findall(r'^- \[x\] `([^`]+)`', backlog, re.M)
    reviewed = re.findall(r'^- \*\*`([^`]+)`\*\*', modules, re.M)
    assert len(expected) == len(set(expected)) == 96
    assert Counter(reviewed) == Counter(expected)


def test_runtime_and_build_exclusions():
    import subprocess
    root=CONTRACT.parent.parent
    targets=["storage/app/users/1/private.jpg","storage/system/backups/updater/db.dump",
             ".env",".env.generated","Models/models/private.bin","PhotoSorter/data/private.jpg"]
    result=subprocess.run(["git","check-ignore","--no-index",*targets],cwd=root,text=True,capture_output=True)
    assert result.returncode==0
    assert set(result.stdout.splitlines())==set(targets)
    dockerignore=(root/".dockerignore").read_text().splitlines()
    assert {"/storage/",".env",".env.generated","Models/","PhotoSorter/data/"}<=set(dockerignore)
    compose=(root/"compose.yaml").read_text()
    assert compose.count("/app:/storage/app")==1
    assert "*app_storage_bind" in compose
    assert "/workspace/PhotoSorter/data" not in compose
    assert "/workspace/Models" not in compose
