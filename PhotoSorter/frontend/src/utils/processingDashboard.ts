import type {Run} from '../types/api'
import {duration} from './format'

/** Dashboard state is server-derived: no optimistic/guessed run progress. */
export function orderedQueue(runs:Run[]):Run[] {
  return runs.filter(r=>r.status==='queued').sort((a,b)=>
    (a.queue_position??Number.MAX_SAFE_INTEGER)-(b.queue_position??Number.MAX_SAFE_INTEGER)
    ||(a.id<b.id?-1:a.id>b.id?1:0))
}

export function activeInference(runs:Run[]):Run|null {
  return runs.find(r=>r.status==='running'||r.status==='stopping')||null
}

export function canRequestStop(run:Run):boolean {
  return run.status==='queued'||run.status==='running'
}

/** No duration or counts unless the server supplies actual measured values. */
export function runDuration(run:Run):string {
  const start=run.actual_started_at
  const end=run.actual_finished_at
  if(!start||!end)return '—'
  const seconds=(new Date(end).getTime()-new Date(start).getTime())/1000
  return Number.isFinite(seconds)&&seconds>=0?duration(seconds):'—'
}

export function runStat(value:number|undefined):string {
  return typeof value==='number'&&Number.isFinite(value)&&value>=0
    ?value.toLocaleString('ru-RU'):'—'
}
