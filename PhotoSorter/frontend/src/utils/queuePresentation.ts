import type {QueueTask,QueueStatus} from '../types/workQueue'

export const STATE_RU:Record<QueueStatus,string>={
  queued:'В очереди',
  running:'Выполняется',
  blocked:'Ожидает решения',
  completed:'Завершено',
  completed_with_errors:'Завершено с ошибками',
  stopped:'Остановлено',
  failed:'Ошибка',
  interrupted:'Прервано'
}
export const isPrep=(item:QueueTask)=>item.kind==='reference_preparation'
export const hasBlockingFailure=(item:QueueTask)=>isPrep(item)&&
  ['failed','interrupted','blocked'].includes(item.state)
export function queuePosition(tasks:readonly QueueTask[],seq:number):number{
  return [...tasks].sort((a,b)=>a.seq-b.seq).findIndex(t=>t.seq===seq)+1
}
export function duration(task:QueueTask,now=Date.now()):string{
  if(!task.started_at)return '—'
  const start=new Date(task.started_at).getTime()
  if(!Number.isFinite(start))return '—'
  const finish=task.finished_at?new Date(task.finished_at).getTime():now
  const minutes=Math.max(0,Math.floor((finish-start)/60000))
  return minutes<60?minutes+' мин':Math.floor(minutes/60)+' ч '+minutes%60+' мин'
}
