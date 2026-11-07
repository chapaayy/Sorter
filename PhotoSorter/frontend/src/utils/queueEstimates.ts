import type {QueueTask,QueueKind} from '../types/workQueue'
import type {Run} from '../types/api'
import {duration} from './format'

export interface TaskEstimate {
  startInSeconds:number|null
  finishInSeconds:number|null
  remainingSeconds:number|null
  durationSeconds:number|null
}

const valid=(n:unknown):n is number=>typeof n==='number'&&Number.isFinite(n)&&n>=0
export function elapsedSeconds(start?:string|null,end?:string|null,now=Date.now()):number|null{
  if(!start)return null
  const a=new Date(start).getTime(),b=end?new Date(end).getTime():now
  return Number.isFinite(a)&&Number.isFinite(b)&&b>=a?(b-a)/1000:null
}

/** Approximate times are rounded UP, never shown as measured facts. */
export function approxDuration(seconds:number|null):string{
  if(!valid(seconds))return '—'
  if(seconds<60)return '≈ 1 мин'
  const minutes=Math.ceil(seconds/60)
  return minutes<60?'≈ '+minutes+' мин':'≈ '+Math.floor(minutes/60)+' ч'+
    (minutes%60?' '+minutes%60+' мин':'')
}
export function actualDuration(start?:string|null,end?:string|null):string{
  if(!start||!end)return '—'
  const seconds=elapsedSeconds(start,end)
  return seconds===null?'—':duration(seconds)
}
function countOf(task:QueueTask):number|null{
  const n=task.kind==='fo_processing'?task.fo_photo_count:task.total_count
  return valid(n)&&n>0?n:null
}
function median(values:number[]):number|null{
  if(!values.length)return null
  const a=[...values].sort((x,y)=>x-y)
  return a.length%2?a[Math.floor(a.length/2)]:(a[a.length/2-1]+a[a.length/2])/2
}
/** Historical per-photo throughput; FO and reference CPU tasks never share rates. */
export function historicalRates(history:readonly QueueTask[]):Record<QueueKind,number|null>{
  const rates:Record<QueueKind,number[]>={fo_processing:[],reference_preparation:[]}
  for(const job of history){
    if(job.state!=='completed')continue
    const count=countOf(job),elapsed=elapsedSeconds(job.started_at,job.finished_at)
    if(count&&elapsed!==null&&elapsed>0){
      const unit=elapsed/count
      if(unit>.01&&unit<3600)rates[job.kind].push(unit)
    }
  }
  return {fo_processing:median(rates.fo_processing.slice(0,30)),
    reference_preparation:median(rates.reference_preparation.slice(0,30))}
}
function durationFromHistory(task:QueueTask,rates:Record<QueueKind,number|null>):number|null{
  const count=countOf(task),rate=rates[task.kind]
  return count&&rate!==null?count*rate:null
}
/** A running FO has its own measured MegaLoc ETA. Never extrapolate a
 * generic stage percentage as if it measured the entire model pipeline. */
function liveRemaining(task:QueueTask,rates:Record<QueueKind,number|null>,now:number):number|null{
  if(task.kind==='fo_processing'){
    const eta=task.fo_progress?.estimated_remaining_seconds
    return valid(eta)?eta:null
  }
  const elapsed=elapsedSeconds(task.started_at,null,now)
  const count=countOf(task),done=task.completed_count
  if(elapsed===null||count===null)return null
  if(valid(done)&&done>=2&&elapsed>=5)return Math.max(0,(count-done)*elapsed/done)
  const expected=durationFromHistory(task,rates)
  return expected!==null?Math.max(0,expected-elapsed):null
}
/** FIFO estimates are a cumulative timeline. Any unknown predecessor, failed
 * preparation or truncated queue invalidates downstream estimates. */
export function estimateQueue(active:readonly QueueTask[],history:readonly QueueTask[],now=Date.now()):Map<number,TaskEstimate>{
  const rates=historicalRates(history)
  const result=new Map<number,TaskEstimate>()
  let cursor:number|null=0
  for(const task of [...active].sort((a,b)=>a.seq-b.seq)){
    if(task.state==='running'){
      const remaining=liveRemaining(task,rates,now)
      result.set(task.seq,{startInSeconds:0,remainingSeconds:remaining,
        durationSeconds:null,finishInSeconds:remaining})
      cursor=cursor!==null&&remaining!==null?cursor+remaining:null
    }else if(task.state==='queued'){
      const own=durationFromHistory(task,rates)
      const start:number|null=cursor
      const finish:number|null=start!==null&&own!==null?start+own:null
      result.set(task.seq,{startInSeconds:start,finishInSeconds:finish,
        remainingSeconds:null,durationSeconds:own})
      cursor=finish
    }else{
      result.set(task.seq,{startInSeconds:null,finishInSeconds:null,
        remainingSeconds:null,durationSeconds:null})
      cursor=null
    }
  }
  return result
}
export function queueTime(task:QueueTask,estimate?:TaskEstimate):{label:string;detail:string}{
  if(task.state==='running'){
    return {label:approxDuration(estimate?.remainingSeconds??null),
      detail:estimate?.remainingSeconds==null?'Время уточняется':'Осталось'}
  }
  if(task.state==='queued'){
    return {label:approxDuration(estimate?.finishInSeconds??null),
      detail:estimate?.finishInSeconds==null?'Время уточняется':(
        estimate.startInSeconds!==null&&estimate.startInSeconds>0
        ?'Старт '+approxDuration(estimate.startInSeconds):'До завершения · включая очередь')}
  }
  if(['completed','completed_with_errors','failed','stopped','interrupted'].includes(task.state)){
    const spent=actualDuration(task.started_at,task.finished_at)
    return {label:spent==='—'?'—':'За '+spent,detail:'Фактическая длительность'}
  }
  return {label:'—',detail:'Ожидает решения'}
}
export function runTime(run?:Run|null,estimate?:TaskEstimate):{label:string;detail:string}{
  if(!run)return {label:'—',detail:'Не обрабатывалось'}
  if(run.status==='queued'){
    return {label:approxDuration(estimate?.finishInSeconds??null),
      detail:estimate?.finishInSeconds==null?'Время уточняется':(
        estimate.startInSeconds!==null&&estimate.startInSeconds>0
        ?'Старт '+approxDuration(estimate.startInSeconds):'До завершения · включая очередь')}
  }
  if(run.status==='running'){
    const eta=estimate?.remainingSeconds??run.progress?.estimated_remaining_seconds
    return {label:approxDuration(valid(eta)?eta:null),
      detail:valid(eta)?'Осталось':'Время уточняется'}
  }
  if(run.status==='stopping')return {label:'—',detail:'Остановка'}
  const spent=actualDuration(run.actual_started_at,run.actual_finished_at)
  return {label:spent==='—'?'—':'За '+spent,detail:'Фактическая длительность'}
}
