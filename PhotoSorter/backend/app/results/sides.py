"""Persist the winning *group* reference's side; no new MegaLoc inference."""
from __future__ import annotations


def attach_sides(rows: list[dict], pinned_members: list[dict]) -> list[dict]:
    paths={member["path"]:(member["sam"],member.get("side")) for member in pinned_members}
    for row in rows:
        winner=(row.get("top") or [{}])[0]
        reference=paths.get(winner.get("reference"))
        row["side"]=reference[1] if reference and reference[0]==winner.get("label") else None
    return rows
