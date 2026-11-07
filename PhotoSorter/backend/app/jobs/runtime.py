"""Standalone job runtime used by the PostgreSQL worker."""

from __future__ import annotations
import copy,threading,time,traceback,uuid
from datetime import datetime,timezone
from pathlib import Path
from ..results.repository import run_path,save_run,load_run,list_runs
from ..recognition.errors import JobCancelled
from ..logging.events import emit
from .progress import record
from .overall_progress import OverallProgress

class Job:
    def __init__(self,info):
        self.info=info; self.path=run_path(info['id'])
        self.cancel_event=threading.Event()
        self.active_model=None
        self.started_monotonic=None; self.overall=OverallProgress()
        self._save_lock=threading.Lock()
        self._saved_snapshot=None
        self._last_progress_save=0.0
        self._last_progress_stage=None
    def save(self):
        with self._save_lock:
            # Keep a committed copy for HTTP polling so it does not repeatedly
            # open run.json on Windows while os.replace is publishing it.
            snapshot=copy.deepcopy(self.info)
            save_run(snapshot)
            self._saved_snapshot=snapshot
    def snapshot(self):
        with self._save_lock:
            return copy.deepcopy(self._saved_snapshot)
    def stopped(self): return self.cancel_event.is_set()
    def log(self,level,message,model=None):emit(self.info['id'],level,message,model)
    def configure_progress(self, references, queries, models):
        self.overall.configure(references, queries, models, self.started_monotonic or time.monotonic())
    def progress(self,model,stage,current,total,detail=''):
        record(self,model,stage,current,total,detail)
    def run(self):
        from .worker import process
        self.started_monotonic=time.monotonic()
        self.info['status']='running';self.save()
        self.log('INFO','Запуск обработки')
        try:
            process(self)
            errors=[x.get('error','Ошибка MegaLoc') for x in self.info['models'].values()
                    if x.get('status')=='error']
            if errors:
                raise RuntimeError('; '.join(errors))
            # Optional server hook: a run is not complete before its ZIP exists.
            finalize=getattr(self,'finalize_results',None)
            if finalize is not None:
                finalize()
            self.info['status']='completed'
        except (InterruptedError,JobCancelled):
            self.info['status']='stopped';self.log('WARNING','Обработка остановлена, готовые результаты сохранены')
        except Exception as exc:
            self.info['status']='failed';self.info['error']=f'{type(exc).__name__}: {exc}'
            self.log('ERROR',f'Ошибка запуска: {self.info["error"]}')
            (self.path/'errors.txt').write_text(traceback.format_exc(),encoding='utf-8')
        finally:
            if self.info['status'] in ('completed','completed_with_errors'):
                progress = self.info.get('progress',{})
                progress.update(self.overall.calculate(time.monotonic(), finished=True))
                progress['stage_label'] = 'Обработка завершена'
            self.info['finished_at']=datetime.now(timezone.utc).isoformat()
            self.save();self.log('INFO',f'Завершено: {self.info["status"]}')

