"""Find FO groups using one MegaLoc cosine threshold, before loading samples.

All normalized FO embeddings are compared once. An undirected edge connects two
FO when their cosine similarity reaches the run's threshold; the connected
components form groups. No pHash, color, EXIF, SAM search or group-merge veto.

Note: transitive connectivity can connect distinct nearby constructions. Keep
pairwise and nearest-other diagnostics so this trade-off is visible to users.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..errors import JobCancelled
from ..math import l2

DEFAULT_COSINE_THRESHOLD = 0.50
MIN_COSINE_THRESHOLD = 0.50
MAX_COSINE_THRESHOLD = 0.99
MAX_RECORDED_PEERS = 20


@dataclass(frozen=True)
class PhotoGroup:
    id: str
    members: tuple[int, ...]
    min_similarity: float | None = None
    mean_similarity: float | None = None
    nearest_other_group: str | None = None
    nearest_other_similarity: float | None = None
    separation_reason: str | None = None
    # A small, bounded set of exact intra-group pairwise MegaLoc scores per FO.
    peers: dict[int, tuple[tuple[int, float], ...]] = field(default_factory=dict)


def find_groups(
    paths: list[Path], features: list[np.ndarray], *, stop=None, progress=None,
    cosine_threshold: float = DEFAULT_COSINE_THRESHOLD,
) -> list[PhotoGroup]:
    """Connected components of all FO cosine similarities >= a single threshold.

    Each FO belongs to exactly one component. Components are stable in source
    order. Similarities come exclusively from the supplied MegaLoc embeddings.
    """
    if len(paths) != len(features):
        raise ValueError('Число ФО и эмбеддингов должно совпадать')
    if not np.isfinite(cosine_threshold) or not MIN_COSINE_THRESHOLD <= cosine_threshold <= MAX_COSINE_THRESHOLD:
        raise ValueError('Порог группировки MegaLoc должен быть от 0.50 до 0.99')
    n = len(paths)
    if not n:
        return []
    if stop and stop():
        raise JobCancelled('Остановлено пользователем')
    vectors = np.stack([l2(feature) for feature in features]).astype(np.float32)
    # A single FO x FO matrix; never call MegaLoc for a pair or for a group.
    cosine = np.clip(vectors @ vectors.T, -1.0, 1.0)
    np.fill_diagonal(cosine, 1.0)

    if progress:
        progress('grouping', 0, n, f'Сравнение всех {n} ФО между собой; порог {cosine_threshold:.2f}')
    # A breadth-first traversal of threshold edges (no group-group checks).
    owners = np.full(n, -1, dtype=np.int32)
    clusters: list[list[int]] = []
    processed = 0
    for seed in range(n):
        if owners[seed] >= 0:
            continue
        if stop and stop():
            raise JobCancelled('Остановлено пользователем')
        group_num = len(clusters)
        owners[seed] = group_num
        queue = [seed]
        position = 0
        while position < len(queue):
            if stop and stop():
                raise JobCancelled('Остановлено пользователем')
            current = queue[position]
            position += 1
            # Every qualifying neighbor joins this component, even if some
            # other members do not match it directly (intended chain behavior).
            neighbors = np.flatnonzero((cosine[current] >= cosine_threshold) & (owners == -1))
            if neighbors.size:
                owners[neighbors] = group_num
                queue.extend(neighbors.tolist())
            processed += 1
            if progress and (processed % 32 == 0 or processed == n):
                progress('grouping', processed, n, f'Сравнено {processed} из {n} ФО')
        clusters.append(sorted(queue))
    # Sorting by earliest source index makes G0001/G0002 stable across runs.
    clusters.sort(key=lambda indices: indices[0])
    for group_num, cluster in enumerate(clusters):
        owners[cluster] = group_num
    if progress:
        progress('grouping_merge', 1, 1, f'Сформировано {len(clusters)} групп ФО')

    # Diagnostics reuse the existing matrix; do NOT merge or split groups.
    nearest: dict[int, tuple[float, int] | None] = {g: None for g in range(len(clusters))}
    if progress:
        progress('grouping_diagnostics', 0, n, 'Расчёт сходства внутри групп ФО')
    for i in range(n):
        if stop and i % 32 == 0 and stop():
            raise JobCancelled('Остановлено пользователем')
        alternatives = np.where(owners != owners[i], cosine[i], -np.inf)
        j = int(np.argmax(alternatives))
        if np.isfinite(alternatives[j]):
            group_num = int(owners[i]); score = float(alternatives[j])
            if nearest[group_num] is None or score > nearest[group_num][0]:
                nearest[group_num] = (score, int(owners[j]))
        if progress and (i + 1) % 64 == 0:
            progress('grouping_diagnostics', i + 1, n, 'Расчёт сходства внутри групп ФО')
    if progress:
        progress('grouping_diagnostics', n, n, 'Группировка ФО завершена')

    answer: list[PhotoGroup] = []
    for group_num, cluster in enumerate(clusters):
        within = cosine[np.ix_(cluster, cluster)]
        upper = within[np.triu_indices(len(cluster), 1)]
        peers = {}
        for local_i, photo_i in enumerate(cluster):
            order = np.argsort(-within[local_i], kind='stable')
            peers[photo_i] = tuple(
                (cluster[int(local_j)], round(float(within[local_i, local_j]), 6))
                for local_j in order if int(local_j) != local_i
            )[:MAX_RECORDED_PEERS]
        other = nearest[group_num]
        answer.append(PhotoGroup(
            id=f'G{group_num + 1:04d}', members=tuple(cluster),
            min_similarity=round(float(upper.min()), 6) if upper.size else None,
            mean_similarity=round(float(upper.mean()), 6) if upper.size else None,
            nearest_other_group=f'G{other[1] + 1:04d}' if other else None,
            nearest_other_similarity=round(other[0], 6) if other else None,
            separation_reason=(f'Сходство всех пар ФО между группами ниже порога {cosine_threshold:.2f}' if other else None),
            peers=peers,
        ))
    return answer
