"""Resolve one SAM per conservative FO group without global SAM exclusivity.

Scores are per-query best-per-SAM similarity. Group scores are arithmetic means,
not percentages or calibrated probabilities. Preserve individual choices for audit.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import numpy as np
from ..grouping.finder import PhotoGroup

# If group members disagree, prefer _Неопределено_ over silently spreading a
# questionable assignment. These are provisional heuristics, not confidence.
MIN_VOTE_RATIO = 2 / 3
MIN_CONFLICT_MARGIN = 0.015


def resolve_groups(paths: list[Path], groups: list[PhotoGroup], label_names: list[str],
                   sam_scores: np.ndarray, reference_for, *, topk=5):
    """Return rows in original FO order; reference_for(photo_idx, sam_idx)->str."""
    if sam_scores.shape != (len(paths), len(label_names)):
        raise ValueError('Размер матрицы SAM не совпадает с количеством ФО и SAM')
    rows: list[dict | None] = [None] * len(paths)
    for group in groups:
        indices = list(group.members)
        sub = sam_scores[indices]
        mean_scores = np.mean(sub, axis=0)
        individual_winners = [int(np.argmax(row)) for row in sub]
        winner = int(np.argmax(mean_scores))
        count_winner = Counter(individual_winners)[winner]
        conflicting = count_winner != len(indices)
        order = sorted(range(len(label_names)), key=lambda k:(-float(mean_scores[k]), label_names[k]))
        margin = float(mean_scores[order[0]] - mean_scores[order[1]]) if len(order)>1 else float('inf')
        accepted = (len(indices)==1 or not conflicting or
                    (count_winner / len(indices) >= MIN_VOTE_RATIO and margin >= MIN_CONFLICT_MARGIN))

        # The displayed sample belongs to the FO which best matched this SAM.
        def group_candidate(k):
            source = max(indices, key=lambda i: float(sam_scores[i, k]))
            return {'label': label_names[k], 'score': round(float(mean_scores[k]), 6),
                    'reference': reference_for(source, k)}

        group_top = [group_candidate(k) for k in order[:topk]]
        for i in indices:
            own_order = sorted(range(len(label_names)),
                               key=lambda k:(-float(sam_scores[i, k]), label_names[k]))
            individual_top = [{'label': label_names[k], 'score': round(float(sam_scores[i, k]), 6),
                               'reference': reference_for(i, k)} for k in own_order[:topk]]
            rows[i] = {
                'query': str(paths[i]),
                'top': group_top if accepted else [],
                'individual_top': individual_top,
                'group_candidates': group_top,
                'group_id': group.id,
                'group_size': len(indices),
                'group_fo_min_similarity': group.min_similarity,
                'group_fo_mean_similarity': group.mean_similarity,
                'nearest_fo_group': group.nearest_other_group,
                'nearest_fo_group_score': group.nearest_other_similarity,
                'group_separation_reason': group.separation_reason,
                'group_members': [str(paths[j]) for j in indices],
                'group_peers': [{'query': str(paths[j]), 'score': score}
                                for j, score in group.peers.get(i, ())],
                'group_status': ('single' if len(indices)==1 else
                                 'assigned' if accepted else 'conflict'),
                'group_score_method': 'mean_best_per_sam',
                'individual_sam': individual_top[0]['label'] if individual_top else None,
            }
            if not accepted:
                rows[i]['reason'] = 'Противоречивые результаты внутри группы ФО'
    return rows
