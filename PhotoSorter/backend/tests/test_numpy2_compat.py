"""Guard against ndarray methods removed by NumPy 2 in deployed code.

The server may use NumPy 2.x after installing PaddleOCR, even if the lean
backend test dependencies use NumPy 1.26. Geometry regression is separately
executed against NumPy 2 in CI.
"""
from __future__ import annotations

import ast
from pathlib import Path


def test_no_removed_ndarray_ptp_calls_in_production():
    root=Path(__file__).resolve().parents[1]
    checked=0
    for folder in ("app","server"):
        for path in (root/folder).rglob("*.py"):
            tree=ast.parse(path.read_text("utf-8"),filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute):
                    continue
                if node.func.attr!="ptp":
                    continue
                target=node.func.value
                assert isinstance(target,ast.Name) and target.id=="np", (
                    f"{path.relative_to(root)}:{node.lineno}: "
                    "NumPy 2 removed ndarray.ptp(); use np.ptp(array, axis=...)"
                )
                checked+=1
    assert checked>=1  # XFeat homography geometry explicitly uses np.ptp.
