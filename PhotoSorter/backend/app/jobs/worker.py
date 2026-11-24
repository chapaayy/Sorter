"""Single MegaLoc run: FO grouping first, SAM matching second, safe export last."""
from __future__ import annotations
import time
import traceback
from ..storage.categories import Category
from ..storage.temporary import pipeline_directory
from pathlib import Path
from ..recognition.engines.megaloc.extractor import MegaLocEngine
from ..recognition.pipeline import match_grouped_megaloc
from ..recognition.errors import JobCancelled
from ..photos.scanner import images, validate
from ..results.repository import save_model
from ..results.match_filter import apply_min_match_score
from ..results.sides import attach_sides

def process(job):
    if job.info.get('has_media_profile'):
        with pipeline_directory(Category.VIDEO_FRAMES, run_id=job.info['id']) as temp:
            from server.media.sorting import MediaQueries
            media=MediaQueries(job,Path(temp))
            _process(job,media)
    else:
        _process(job,None)

def _process(job,media):
    info=job.info
    job.log('INFO','Сканирование папок и проверка изображений')
    scan_started=time.perf_counter()
    # Only the immutable version pinned on FIFO claim can be consumed.
    refs=[(Path(member["path"]),member["sam"]) for member in info["reference_members"]]
    all_queries=media.photos if media is not None else images(Path(info['new_photos']))
    scan_seconds=round(time.perf_counter()-scan_started,3)
    stamps={str(path):(path.stat().st_size,path.stat().st_mtime_ns) for path in all_queries}
    frames=media.frame_paths if media is not None else []
    job.configure_progress(len(refs),len(all_queries)+len(frames),['megaloc'])
    if not refs:raise ValueError('Нет Образцов для сопоставления')
    # Do not load reference image bytes before FO groups have been formed.
    job.progress(None,'validate_queries',0,len(all_queries),'Проверка ФО')
    validation_started=time.perf_counter()
    queries,invalid_queries=validate(all_queries,
        progress=lambda a,b,c:job.progress(None,'validate_queries',a,b,c),
        should_stop=job.stopped,warn=lambda msg:job.log('WARNING',msg))
    validation_seconds=round(time.perf_counter()-validation_started,3)
    if not queries and media is None:raise ValueError('Нет читаемых ФО')
    info['counts']={'references':len(refs),'queries':len(all_queries),
                    'invalid_references':0,'invalid_queries':len(invalid_queries)}
    job.save()
    name='megaloc'
    job.active_model=name
    warm=getattr(job,'warm_megaloc',None)
    fingerprint=info.get('model_signature')
    already_loaded=warm is not None and warm.ready_for(fingerprint)
    if not already_loaded:
        job.progress(name,'loading',0,1,'Загрузка MegaLoc')
    started=time.monotonic()
    engine=None
    timings={'scan_seconds':scan_seconds,'validate_fo_seconds':validation_seconds}
    try:
        load_started=time.perf_counter()
        engine=warm.get(fingerprint) if warm is not None else MegaLocEngine()
        from server.reference_cache import ReferenceCachedMegaLoc
        engine=ReferenceCachedMegaLoc(engine)
        timings['model_load_seconds']=round(time.perf_counter()-load_started,3)
        if already_loaded:
            job.overall.update(name,'loading',1,1,time.monotonic())
        else:
            job.progress(name,'loading',1,1,'MegaLoc загружена')
        job.log('INFO',f'Устройство: {engine.device}',name)
        config=getattr(engine,'performance',None)
        if config is not None:
            job.log('INFO',f'CPU: {config.threads} потоков, пакет {config.batch_size} ФО, '
                     f'потоков подготовки {config.prefetch_workers}',name)
        rows=match_grouped_megaloc(
            engine,refs,[*queries,*frames],topk=5,stop=job.stopped,
            **({"grouping_fn":media.grouping} if media is not None else {}),
            progress=lambda stage,a,b,c:job.progress(name,stage,a,b,c),
            log=lambda level,msg:job.log(level,msg,name),
            cosine_threshold=info['grouping_threshold'], timings=timings)
        if job.stopped():raise JobCancelled('Остановлено пользователем')
        by_path={row['query']:row for row in rows}
        rows=[by_path.get(str(path),{'query':str(path),'top':[],
              'error':invalid_queries.get(str(path),'Не удалось прочитать ФО')})
              for path in [*all_queries,*frames]]
        if media is not None:
            rows=media.collapse(rows)
            info['media_errors']=media.errors
        if not rows:raise ValueError('Нет готовых файлов для результата')
        # Classification gate only: MegaLoc inference and FO grouping are complete.
        # Old runs without this snapshot parameter keep the historical behavior.
        minimum=float(info.get('min_match_score') or 0.0)
        rows=apply_min_match_score(rows,minimum)
        # The pinned winner reference supplies a folder label only.
        # MegaLoc group/SAM scoring is untouched.
        rows=attach_sides(rows,info['reference_members'])
        filtered=sum(bool(row.get('match_rejected')) for row in rows)
        if minimum>0:
            job.log('INFO',f'Минимальное сходство с образцами: {minimum:.3f}; '
                    f'в Неопределено по порогу: {filtered}',name)
        job.progress(name,'saving',0,len(rows),'Сохранение готовых файлов')
        save_started=time.perf_counter()
        result=save_model(info,name,rows,query_stamps=stamps,
             progress=lambda a,b,c:job.progress(name,'saving',a,b,c),
             on_export_start=lambda:job.progress(name,'export',0,1,'Запись результатов'))
        job.progress(name,'export',1,1,'Манифест сохранён')
        timings['save_seconds']=round(time.perf_counter()-save_started,3)
        timings['reference_cache_hits']=engine.reference_cache_hits
        timings['reference_cache_misses']=engine.reference_cache_misses
        job.log('INFO',f'Образцы: из кэша — {engine.reference_cache_hits}, '
                f'потребовали пересчёта — {engine.reference_cache_misses}',name)
        job.log('INFO','Замеры: '+', '.join(f'{key}={value}' for key,value in timings.items()),name)
        seconds=round(time.monotonic()-started,2)
        info['models'][name]={'status':'completed','device':engine.device,
             'seconds':seconds,'processed':len(result),
             'assigned':sum(bool(row.get('top')) for row in result),
             'filtered':filtered,
             'uncertain':sum(not row.get('top') for row in result),
             'feature_policy':'fo_recomputed_reference_cache',
             'performance':timings,
             'grouping':'megaloc_threshold_components_v3',
             'groups':len({r['group_id'] for r in result if r.get('group_id')})}
        job.log('INFO',f'Готово: {len(result)} ФО за {seconds} с; признаки ФО вычислены для этого запуска',name)
    except JobCancelled:
        raise
    except Exception as exc:
        info['models'][name]={'status':'error','error':f'{type(exc).__name__}: {exc}'}
        job.log('ERROR',f'MegaLoc не завершена: {type(exc).__name__}: {exc}',name)
    finally:
        if engine is not None and warm is None:
            try:engine.unload()
            except Exception as exc:job.log('WARNING',f'Освобождение ресурсов: {exc}',name)
        job.active_model=None
        job.save()
