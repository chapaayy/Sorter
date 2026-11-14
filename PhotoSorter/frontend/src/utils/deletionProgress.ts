import type {DeletionProgress} from '../types/api'

const stages:Record<DeletionProgress['phase'],string>={
  queued:'В очереди на удаление',
  stopping_jobs:'Ожидаем остановки MegaLoc',
  waiting_operations:'Ожидаем завершения скачивания или другой операции',
  scanning:'Подсчитываем файлы и результаты',
  files:'Удаляем оригиналы, результаты и временные файлы',
  database:'Удаляем записи партии',
  completed:'Партия удалена'
}

export function deletionProgress(state?:string|null,progress?:DeletionProgress|null,pending=false){
  const failed=state==='delete_failed'
  const deleting=!failed&&state!=='deleted'&&(pending||state==='deleting')
  const phase=progress?.phase
  const percent=progress?.total&&progress.total>0
    ?Math.min(phase==='completed'?100:99,Math.max(0,Math.floor(100*progress.done/progress.total))):null
  return {
    deleting,failed,inProgress:deleting&&phase==='scanning',
    stage:failed?'Удаление не завершено · проверьте журнал':(phase&&stages[phase])||stages.queued,
    percent:deleting||failed?percent:null
  }
}
