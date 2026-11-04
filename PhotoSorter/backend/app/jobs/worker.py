"""Single MegaLoc run: FO grouping first, SAM matching second, safe export last."""
from __future__ import annotations
import time
import os
import traceback
from pathlib import Path
from ..recognition.engines.megaloc.extractor import MegaLocEngine
from ..recognition.pipeline import match_grouped_megaloc
from ..recognition.errors import JobCancelled
from ..photos.scanner import images, references, validate
from ..results.repository import save_model

def process(job):
    info=job.info
    job.log('INFO','Сканирование папок и проверка изображений')
    scan_started=time.perf_counter()
    refs=references(Path(info['references']),warn=lambda s:job.log('WARNING',s))
    all_queries=images(Path(info['new_photos']))
    scan_seconds=round(time.perf_counter()-scan_started,3)
    stamps={str(path):(path.stat().st_size,path.stat().st_mtime_ns) for path in all_queries}
    job.configure_progress(len(refs),len(all_queries),['megaloc'])
    if not refs:raise ValueError('Нет Образцов для сопоставления')
    # Do not load reference image bytes before FO groups have been formed.
    job.progress(None,'validate_queries',0,len(all_queries),'Проверка ФО')
    validation_started=time.perf_counter()
    queries,invalid_queries=validate(all_queries,
        progress=lambda a,b,c:job.progress(None,'validate_queries',a,b,c),
        should_stop=job.stopped,warn=lambda msg:job.log('WARNING',msg))
    validation_seconds=round(time.perf_counter()-validation_started,3)
    if not queries:raise ValueError('Нет читаемых ФО')
    info['counts']={'references':len(refs),'queries':len(all_queries),
                    'invalid_references':0,'invalid_queries':len(invalid_queries)}
    job.save()
    name='megaloc'
    job.active_model=name
    job.progress(name,'loading',0,1,'Загрузка MegaLoc')
    started=time.monotonic()
    engine=None
    timings={'scan_seconds':scan_seconds,'validate_fo_seconds':validation_seconds}
    try:
        load_started=time.perf_counter()
        engine=MegaLocEngine()
        if os.environ.get("PHOTOSORTER_REFERENCE_CACHE") == "1":
            from server.reference_cache import ReferenceCachedMegaLoc
            engine=ReferenceCachedMegaLoc(engine)
        timings['model_load_seconds']=round(time.perf_counter()-load_started,3)
        job.progress(name,'loading',1,1,'MegaLoc загружена')
        job.log('INFO',f'Устройство: {engine.device}',name)
        config=getattr(engine,'performance',None)
        if config is not None:
            job.log('INFO',f'CPU: {config.threads} потоков, пакет {config.batch_size} ФО, '
                     f'потоков подготовки {config.prefetch_workers}',name)
        rows=match_grouped_megaloc(
            engine,refs,queries,topk=5,stop=job.stopped,
            progress=lambda stage,a,b,c:job.progress(name,stage,a,b,c),
            log=lambda level,msg:job.log(level,msg,name),
            cosine_threshold=info['grouping_threshold'], timings=timings)
        if job.stopped():raise JobCancelled('Остановлено пользователем')
        by_path={row['query']:row for row in rows}
        rows=[by_path.get(str(path),{'query':str(path),'top':[],
              'error':invalid_queries.get(str(path),'Не удалось прочитать ФО')})
              for path in all_queries]
        job.progress(name,'saving',0,len(rows),'Копирование Готовых фоток')
        save_started=time.perf_counter()
        result=save_model(info,name,rows,query_stamps=stamps,
             progress=lambda a,b,c:job.progress(name,'saving',a,b,c),
             on_export_start=lambda:job.progress(name,'export',0,1,'Запись результатов'))
        job.progress(name,'export',1,1,'Манифест сохранён')
        timings['save_seconds']=round(time.perf_counter()-save_started,3)
        job.log('INFO','Замеры: '+', '.join(f'{key}={value}' for key,value in timings.items()),name)
        seconds=round(time.monotonic()-started,2)
        info['models'][name]={'status':'completed','device':engine.device,
             'seconds':seconds,'processed':len(result),
             'assigned':sum(bool(row.get('top')) for row in result),
             'uncertain':sum(not row.get('top') for row in result),
             'feature_policy':'recompute_every_run',
             'performance':timings,
             'grouping':'megaloc_threshold_components_v3',
             'groups':len({r['group_id'] for r in result if r.get('group_id')})}
        job.log('INFO',f'Готово: {len(result)} ФО за {seconds} с; признаки пересчитаны заново',name)
    except JobCancelled:
        raise
    except Exception as exc:
        info['models'][name]={'status':'error','error':f'{type(exc).__name__}: {exc}'}
        job.log('ERROR',f'MegaLoc не завершена: {type(exc).__name__}: {exc}',name)
        with (job.path/'errors.txt').open('a',encoding='utf8') as file:
            file.write(f'\n=== {name} ===\n{traceback.format_exc()}\n')
    finally:
        if engine is not None:
            try:engine.unload()
            except Exception as exc:job.log('WARNING',f'Освобождение ресурсов: {exc}',name)
        job.active_model=None
        job.save()
