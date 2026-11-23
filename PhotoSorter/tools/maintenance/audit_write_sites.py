"""Static discovery of potential file-write sites; metadata only.

This supplements the host snapshot by showing code paths which may create
short-lived files between scans. It is NOT a guarantee of actual runtime writes.
"""
from __future__ import annotations

import ast
import csv
import re
from pathlib import Path

CALLS = {
    "open": "file_open",
    "os.open": "file_open",
    "Path.open": "file_open",
    "tempfile.NamedTemporaryFile": "temporary_file",
    "tempfile.TemporaryFile": "temporary_file",
    "tempfile.TemporaryDirectory": "temporary_directory",
    "tempfile.mkstemp": "temporary_file",
    "tempfile.mkdtemp": "temporary_directory",
    "os.replace": "move_replace",
    "os.rename": "move_replace",
    "os.link": "hardlink",
    "os.symlink": "symlink",
    "shutil.copy": "copy",
    "shutil.copy2": "copy",
    "shutil.copyfile": "copy",
    "shutil.copytree": "copy",
    "shutil.move": "move_replace",
    "shutil.rmtree": "delete",
    "os.unlink": "delete",
    "os.remove": "delete",
    "torch.save": "model_cache",
    "numpy.save": "model_cache",
    "np.save": "model_cache",
    "subprocess.run": "external_process_possible_write",
    "subprocess.Popen": "external_process_possible_write",
    "subprocess.check_call": "external_process_possible_write",
    "subprocess.check_output": "external_process_possible_write",
    "zipfile.ZipFile": "archive",
}
TAILS = {
    "write_text": "write",
    "write_bytes": "write",
    "writelines": "write",
    "mkdir": "directory",
    "touch": "create",
    "save": "possible_write",
    "rename": "move_replace",
    "replace": "move_replace",
    "unlink": "delete",
    "rmdir": "delete",
    "copy": "copy",
}
SHELL = re.compile(r'\b(mkdir|mktemp|touch|cp|mv|rsync|tee|install|tar|unzip|docker|git|chown|chmod)\b|(^|[^>])>{1,2}\s*', re.I)

def _func_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _func_name(node.value)
        return (prefix + "." if prefix else "") + node.attr
    return ""

def _site(node):
    name = _func_name(node.func)
    if name in CALLS:
        kind = CALLS[name]
    elif "." in name and name.rsplit(".", 1)[-1] in TAILS:
        kind = TAILS[name.rsplit(".", 1)[-1]]
    else:
        return None
    if name == "open" or name.endswith(".open"):
        mode = None
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            mode = node.args[1].value
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
        if isinstance(mode, str) and not any(ch in mode for ch in "wax+"):
            return None
        kind = "file_open_possible_write" if mode is None else "file_open_write"
    return name, kind

def collect(project: Path):
    rows = []
    for file in sorted(project.rglob("*")):
        if any(p in ("node_modules", "__pycache__", ".git", "tests", "frontend") for p in file.parts):
            continue
        if file.suffix == ".py":
            try:
                tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
            except (SyntaxError, UnicodeError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    hit = _site(node)
                    if hit:
                        rows.append((str(file.relative_to(project)), node.lineno, hit[0], hit[1]))
        elif file.suffix == ".sh":
            try:
                lines = file.read_text(encoding="utf-8").splitlines()
            except (UnicodeError, OSError):
                continue
            for i, line in enumerate(lines, 1):
                if not line.lstrip().startswith("#") and SHELL.search(line):
                    rows.append((str(file.relative_to(project)), i, "shell", "shell_possible_write"))
    return rows

def export_csv(project: Path, dest: Path):
    rows = collect(project)
    with dest.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out, delimiter=";", lineterminator="\n")
        writer.writerow(("source_file", "line", "operation", "effect"))
        writer.writerows(rows)
    return len(rows)
