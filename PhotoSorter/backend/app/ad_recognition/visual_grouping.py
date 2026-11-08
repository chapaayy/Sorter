"""DINOv2-only advertisement grouping, before any layout or text comparison.

Connected components use the same single-link cosine rule as MegaLoc.  Only
screens with the SAME construction and physical screen ID can form edges.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite

import numpy as np

MAX_DIAGNOSTIC_PEERS = 20
VERSION = "dinov2-visual-components-v1"


def group_screens(screens: list[dict], threshold: float) -> list[dict]:
    if not isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Порог группировки рекламы должен быть от 0 до 1")
    scopes = defaultdict(list)
    for item in screens:
        vector = np.asarray(item["feature"], dtype=np.float32).reshape(-1)
        if vector.shape != (384,) or not np.isfinite(vector).all():
            raise ValueError("Некорректный DINOv2-вектор экрана")
        norm = float(np.linalg.norm(vector))
        if norm <= 1e-8:
            raise ValueError("Пустой DINOv2-вектор экрана")
        scopes[(str(item["sam"]), str(item["screen_id"]))].append({
            **item, "feature": vector / norm
        })

    output = []
    for (sam, screen_id), unsorted in sorted(scopes.items()):
        items = sorted(unsorted, key=lambda it: (it["index"], it["screen_id"]))
        n = len(items)
        matrix = np.clip(
            np.stack([it["feature"] for it in items]) @
            np.stack([it["feature"] for it in items]).T, -1.0, 1.0
        )
        np.fill_diagonal(matrix, 1.0)
        owners = np.full(n, -1, dtype=np.int32)
        parent: dict[int, tuple[int, float]] = {}
        clusters: list[list[int]] = []
        for seed in range(n):
            if owners[seed] >= 0:
                continue
            number = len(clusters)
            owners[seed] = number
            queue = [seed]
            head = 0
            while head < len(queue):
                current = queue[head]
                head += 1
                # Connected components; a weak pair may be linked by a third photo.
                neighbors = np.flatnonzero(
                    (matrix[current] >= threshold) & (owners == -1)
                )
                for other in neighbors.tolist():
                    parent[other] = (current, round(float(matrix[current, other]), 6))
                    owners[other] = number
                    queue.append(other)
            clusters.append(sorted(queue))

        for number, cluster in enumerate(clusters):
            pairs = matrix[np.ix_(cluster, cluster)]
            upper = pairs[np.triu_indices(len(cluster), 1)]
            members = []
            closest_other = None
            for local in cluster:
                item = items[local]
                peers = sorted(
                    (int(peer) for peer in cluster if peer != local),
                    key=lambda peer: (-float(matrix[local, peer]), items[peer]["index"])
                )
                other_candidates = np.flatnonzero(owners != number)
                strongest = (
                    max(other_candidates.tolist(),
                        key=lambda other: float(matrix[local, other]))
                    if other_candidates.size else None
                )
                if strongest is not None:
                    similarity = round(float(matrix[local, strongest]), 6)
                    if closest_other is None or similarity > closest_other[0]:
                        closest_other = (similarity, int(owners[strongest]))
                via = parent.get(local)
                members.append({
                    "index": int(item["index"]),
                    "screen_id": screen_id,
                    "assigned_sam": sam,
                    "screen_name": item.get("screen_name"),
                    "annotation_id": item.get("annotation_id"),
                    "embedding_file": item["embedding_file"],
                    "joined_via": {
                        "index": items[via[0]]["index"],
                        "screen_id": screen_id,
                        "similarity": via[1]
                    } if via else None,
                    "nearest_peers": [
                        {"index": items[peer]["index"], "screen_id": screen_id,
                         "similarity": round(float(matrix[local, peer]), 6)}
                        for peer in peers[:MAX_DIAGNOSTIC_PEERS]
                    ],
                    "nearest_separate": {
                        "index": items[strongest]["index"],
                        "screen_id": screen_id,
                        "similarity": round(float(matrix[local, strongest]), 6)
                    } if strongest is not None else None
                })
            output.append({
                "assigned_sam": sam,
                "screen_id": screen_id,
                "threshold": threshold,
                "members": members,
                "member_count": len(members),
                "min_pairwise_similarity": (
                    round(float(upper.min()), 6) if upper.size else None),
                "mean_pairwise_similarity": (
                    round(float(upper.mean()), 6) if upper.size else None),
                "nearest_other_similarity": closest_other[0] if closest_other else None,
                "_scope": (sam, screen_id),
                "_local_group": number,
                "_nearest_local_group": closest_other[1] if closest_other else None
            })

    # Stable IDs depend only on the screen/photo input order, not layout versions.
    output.sort(key=lambda group: (
        group["members"][0]["index"], group["screen_id"], group["assigned_sam"]))
    identities = {}
    for number, group in enumerate(output, 1):
        group["id"] = f"R{number:04d}"
        identities[(group["_scope"], group["_local_group"])] = group["id"]
    for group in output:
        nearest = group.pop("_nearest_local_group")
        scope = group.pop("_scope")
        group.pop("_local_group")
        group["nearest_other_group"] = (
            identities[(scope, nearest)] if nearest is not None else None)
        group["separation_reason"] = (
            f"Между группами одного экрана нет ребра с cosine >= {threshold:.2f}"
            if nearest is not None else
            "Других визуальных групп этого физического экрана нет")
        group["formation_reason"] = (
            f"Связные компоненты DINOv2: cosine >= {threshold:.2f}; "
            "другие конструкции и физические экраны не сравниваются")
    return output
