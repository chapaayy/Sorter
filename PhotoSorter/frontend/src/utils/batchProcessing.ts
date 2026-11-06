import type {Batch,Run} from '../types/api'
import {canProcessBatch} from './batches'
import {isActive,runLabels} from './format'

export type ProcessingTone='ok'|'danger'|'neutral'
export interface BatchProcessingPresentation {
  label:string
  tone:ProcessingTone
  detail:string
  run:Run|null
  canStart:boolean
  canStop:boolean
  canCancelAuto:boolean
  resultId:string|null
  overallPercent:number|null
  stagePercent:number|null
  stageLabel:string
  stageCounts:string|null
}
const measured=(value:unknown):number|null=>
  typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100?value:null

/** One source of truth for FO list and FO gallery; never infer MegaLoc state
 * from thumbnail_state or the number of photos alone. */
export function batchProcessing(batch:Batch):BatchProcessingPresentation {
  const run=batch.latest_run??null
  const active=!!run&&isActive(run.status)
  const resultId=batch.last_result_run_id||
    (run&&['completed','completed_with_errors'].includes(run.status)?run.id:null)
  let label='Не обработано'
  let tone:ProcessingTone='neutral'
  let detail='MegaLoc ещё не запускался'
  if(batch.delete_state!=='active'){
    label='Удаление партии';detail='Партия недоступна'
  }else if(run){
    label=runLabels[run.status]||'Неизвестный статус'
    if(run.status==='completed')tone='ok'
    if(run.status==='failed'||run.status==='completed_with_errors')tone='danger'
    if(run.status==='queued')
      detail=run.queue_position!=null?'Очередь MegaLoc · позиция '+run.queue_position:'В очереди MegaLoc'
    else if(run.status==='running'||run.status==='stopping')
      detail=run.progress?.stage_label||run.progress?.stage||'Выполняется MegaLoc'
    else if(run.status==='failed'||run.status==='completed_with_errors')
      detail=run.error||'Проверьте журнал запуска'
    else if(run.status==='completed')
      detail='Сортировка успешно завершена'
    else detail='Запуск остановлен или прерван'
  }else if(batch.upload_manifest_state==='waiting'||(batch.pending??0)>0){
    label='Загрузка не завершена'
    detail='Нужны все исходные фотографии партии'
  }else if(batch.auto_process_state==='waiting'){
    label='Ожидает автозапуска'
    detail=batch.auto_process_error||'MegaLoc автоматически появится в очереди'
  }else if((batch.runs??0)>0){
    label='Есть история запусков'
    detail='Откройте историю обработок партии'
  }else if((batch.photos??0)===0){
    label='Нет фотографий'
    detail='Загрузите исходную папку ФО'
  }else{
    detail='Готова к запуску MegaLoc'
  }
  const p=run?.progress
  const counts=p?.total!=null&&p.total>0&&p.current!=null
    ?p.current+' из '+p.total+' на этапе':null
  return {
    label,tone,detail,run,
    canStart:batch.delete_state==='active'&&canProcessBatch(batch)&&!active,
    canStop:batch.delete_state==='active'&&(run?.status==='queued'||run?.status==='running'),
    canCancelAuto:batch.delete_state==='active'&&batch.auto_process_state==='waiting'&&!active,
    resultId:resultId??null,
    overallPercent:run?.status==='running'?measured(p?.overall_percent):null,
    stagePercent:run?.status==='running'?measured(p?.stage_percent):null,
    stageLabel:p?.stage_label||p?.stage||'MegaLoc',
    stageCounts:counts
  }
}
export function batchThreshold(batch:Batch):number {
  const candidate=batch.latest_run?.grouping_threshold??batch.auto_process_threshold??.50
  return Number.isFinite(candidate)&&candidate>=.50&&candidate<=.99?candidate:.50
}
