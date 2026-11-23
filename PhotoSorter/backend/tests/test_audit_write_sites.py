"""Potential file-write discovery must never parse users' uploaded photos."""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "maintenance" / "audit_write_sites.py"
spec = importlib.util.spec_from_file_location("write_site_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


def test_python_shell_docker_write_sites_without_reading_user_data(tmp_path):
    backend = tmp_path / "PhotoSorter" / "backend" / "server"
    backend.mkdir(parents=True)
    source = backend / "writer.py"
    source.write_text(
        'from pathlib import Path\n'
        'from tempfile import NamedTemporaryFile\n'
        'Path("x").write_bytes(b"a")\n'
        'with open("x","wb") as f:\n'
        '    f.write(b"a")\n'
        'with NamedTemporaryFile() as f:\n'
        '    pass\n'
    )
    shell = tmp_path / "PhotoSorter" / "tools" / "maintenance" / "install.sh"
    shell.parent.mkdir(parents=True)
    shell.write_text('mkdir -p /tmp/example\n')
    dockerfile = tmp_path / "PhotoSorter" / "docker" / "app" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text('FROM alpine\nRUN touch /tmp/test\n')
    user_path = tmp_path / "PhotoSorter" / "data" / "uploads" / "b" / "untrusted.py"
    user_path.parent.mkdir(parents=True)
    user_path.write_bytes(b"\xff\xfeinvalid source; should not be opened")

    rows = audit.collect(tmp_path)
    assert rows
    assert any("writer.py" in row[0] and row[2].endswith("write_bytes") for row in rows)
    assert any("writer.py" in row[0] and row[2] == "open" for row in rows)
    assert any("install.sh" in row[0] and row[2] == "shell" for row in rows)
    assert any("Dockerfile" in row[0] and row[2] == "docker_build" for row in rows)
    assert not any("untrusted.py" in row[0] for row in rows)
