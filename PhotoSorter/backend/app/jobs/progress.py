"""Expose both stage progress and adaptive overall run completion."""
import time
from .overall_progress import STAGE_LABELS


def record(job, model, stage, current, total, detail):
    now = time.monotonic()
    total = max(0,int(total))
    current = max(0,min(total,int(current)))
    name = STAGE_LABELS.get(stage, stage)
    progress = {'model':model,'stage':stage,'stage_label':name,
                'current':current,'total':total,'detail':detail,
                'stage_percent':round(current/total*100,1) if total else None}
    if job.started_monotonic is not None:
        progress['elapsed_seconds']=round(max(0,now-job.started_monotonic),1)
    if hasattr(job,'overall'):
        job.overall.update(model,stage,current,total,now)
        phase=next((p for p in job.overall.phases
                    if p.model==model and p.stage==stage),None)
        if phase and phase.started_at is not None and current>=2:
            elapsed=max(0.0,now-phase.started_at)
            if elapsed>=0.1:
                progress['stage_items_per_second']=round(current/elapsed,2)
        progress.update(job.overall.calculate(now))
    job.info['progress']=progress
    should_save=(stage!=job._last_progress_stage or current==total or
                 now-job._last_progress_save>=0.5)
    if should_save:
        job.save()
        job._last_progress_save=now
        job._last_progress_stage=stage
