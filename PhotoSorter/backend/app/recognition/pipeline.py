"""One-pass MegaLoc embeddings -> FO groups -> group-wise SAM matching.

All neural embeddings exist only in RAM during this run; the shared
reference-score matrix is computed in vectorized batches to reduce CPU work.
"""
from __future__ import annotations
from pathlib import Path
import time
import numpy as np
from .errors import JobCancelled
from .math import l2
from .grouping.finder import find_groups, DEFAULT_COSINE_THRESHOLD
from .matching.resolver import resolve_groups


def match_grouped_megaloc(engine, references, queries, *, topk=5,
                          stop=None, progress=None, log=None,
                          grouping_fn=find_groups, cosine_threshold: float = DEFAULT_COSINE_THRESHOLD,
                          timings: dict | None = None):
    def check_stop():
        if stop and stop(): raise JobCancelled('Остановлено пользователем')

    def extract_all(paths):
        """MegaLoc uses bounded batch inference; simple test/legacy engines keep extract()."""
        if callable(getattr(engine, 'extract_many', None)):
            yield from engine.extract_many(paths, stop=stop)
        else:
            for path in paths:
                check_stop()
                try: yield Path(path), engine.extract(path), None
                except Exception as exc: yield Path(path), None, exc

    started = time.perf_counter()
    if progress: progress('queries',0,len(queries),'Вычисление признаков ФО')
    good_paths=[]; vectors=[]; failed={}
    for i,(path,feature,error) in enumerate(extract_all(queries),1):
        check_stop()
        if error is None:
            vectors.append(l2(feature))
            good_paths.append(Path(path))
        else:
            failed[str(path)] = f'{type(error).__name__}: {error}'
            if log: log('WARNING', f'MegaLoc: пропущена ФО {path}: {error}')
        if progress: progress('queries',i,len(queries),Path(path).name)
    if timings is not None:
        timings['extract_fo_seconds'] = round(time.perf_counter()-started, 3)
        timings['extracted_fo'] = len(good_paths)

    # Group ALL input FO before accessing a reference image.
    started = time.perf_counter()
    groups=grouping_fn(good_paths, vectors, stop=stop, progress=progress,
                       cosine_threshold=cosine_threshold) if good_paths else []
    if timings is not None:
        timings['grouping_seconds'] = round(time.perf_counter()-started, 3)
        timings['groups'] = len(groups)
    if log:
        log('INFO',f'Группировка только MegaLoc: {len(good_paths)} ФО, {len(groups)} групп, '
                   f'{sum(len(g.members)>1 for g in groups)} групп с несколькими ФО, порог {cosine_threshold:.2f}')

    started = time.perf_counter()
    if progress: progress('references',0,len(references),'Группировка завершена. Подготовка Образцов')
    loaded_references=[]
    reference_paths = [Path(path) for path, _ in references]
    for i,(record, extracted) in enumerate(zip(references, extract_all(reference_paths), strict=True),1):
        (path,label), (_, feature, error) = record, extracted
        check_stop()
        if error is None:
            loaded_references.append((Path(path), label, l2(feature)))
        else:
            if log: log('WARNING', f'MegaLoc: пропущен Образец {path}: {error}')
        if progress: progress('references',i,len(references),Path(path).name)
    if timings is not None:
        timings['extract_references_seconds'] = round(time.perf_counter()-started, 3)
        timings['extracted_references'] = len(loaded_references)
    if not loaded_references: raise ValueError('Не удалось извлечь признаки Образцов')

    if not good_paths:
        return [{'query':str(path),'top':[],'error':failed[str(path)]}
                for path in queries]

    started = time.perf_counter()
    # Group reference vectors by SAM to compute max per SAM with reduceat.
    ordered=sorted(loaded_references, key=lambda record:(record[1],str(record[0])))
    labels=[]; starts=[]; paths=[]; features=[]
    for path,label,feature in ordered:
        if not labels or labels[-1]!=label:
            labels.append(label); starts.append(len(paths))
        paths.append(path); features.append(feature)
    reference_matrix=np.stack(features).astype(np.float32)
    query_matrix=np.stack(vectors).astype(np.float32)
    scores=np.empty((len(good_paths),len(labels)),dtype=np.float32)
    starts_np=np.asarray(starts,dtype=np.int64)
    if progress: progress('matching',0,len(good_paths),'Сравнение групп ФО с Образцами')
    for begin in range(0,len(good_paths),32):
        check_stop()
        end=min(begin+32,len(good_paths))
        block=query_matrix[begin:end] @ reference_matrix.T
        scores[begin:end]=np.maximum.reduceat(block,starts_np,axis=1)
        if progress: progress('matching',end,len(good_paths),good_paths[end-1].name)
    ends=starts[1:]+[len(paths)]

    def reference_for(photo_idx:int,sam_idx:int)->str:
        first,last=starts[sam_idx],ends[sam_idx]
        similarities=reference_matrix[first:last] @ query_matrix[photo_idx]
        return str(paths[first+int(np.argmax(similarities))])

    grouped_rows=resolve_groups(good_paths, groups, labels, scores, reference_for, topk=topk)
    if timings is not None:
        timings['matching_seconds'] = round(time.perf_counter()-started, 3)
    lookup={row['query']:row for row in grouped_rows}
    for path,message in failed.items():lookup[path]={'query':path,'top':[],'error':message}
    return [lookup[str(path)] for path in queries]
