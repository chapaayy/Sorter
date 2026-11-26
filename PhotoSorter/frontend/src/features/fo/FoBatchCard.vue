<script setup lang="ts">
import {useSessionStore} from '../../stores/session'
import {computed} from 'vue'
import type {Batch} from '../../types/api'
import type {TaskEstimate} from '../../utils/queueEstimates'
import {approxDuration,runTime} from '../../utils/queueEstimates'
import {batchProcessing,batchThreshold} from '../../utils/batchProcessing'
import {bytes,date,readyToStart} from '../../utils/format'
import {deletionProgress} from '../../utils/deletionProgress'
import type {UploadRow} from '../../types/uploadQueue'
import {uploadPercent,uploadStatusLabel} from '../../utils/transferPresentation'
import CompactTaskCard from '../../components/ui/CompactTaskCard.vue'

const props=defineProps<{batch:Batch;position:number;estimate?:TaskEstimate;busy?:boolean;deleting?:boolean;upload?:UploadRow}>()
const emit=defineEmits<{
  (e:'start',batchId:string,threshold:number):void
  (e:'stop',runId:string):void
  (e:'cancelAuto',batchId:string):void
  (e:'showUploads'):void
}>()
const session=useSessionStore()
const allowed=(key:string)=>session.can(key,props.batch.owner_id)
const state=computed(()=>batchProcessing(props.batch))
const run=computed(()=>state.value.run)
const timing=computed(()=>{
  const media=props.batch.media_preparation
  return media?.state==='running'
    ?{label:approxDuration(media.eta_seconds??null),detail:media.eta_seconds==null?'Время уточняется':'Осталось'}
    :runTime(run.value,props.estimate)
})
const removal=computed(()=>deletionProgress(props.batch.delete_state,props.batch.deletion_progress,props.deleting))
const transfer=computed(()=>props.batch.delete_state==='active'&&!removal.value.deleting?props.upload:undefined)
const statusTone=computed(()=>{
  if(removal.value.failed)return 'danger'
  if(removal.value.deleting)return 'deleting'
  if(transfer.value){
    if(transfer.value.status==='running')return 'running'
    if(transfer.value.status==='waiting')return 'queued'
    if(transfer.value.status==='failed')return 'danger'
    return 'neutral'
  }
  const media=props.batch.media_preparation?.state
  if(media==='running')return 'running'
  if(media==='queued')return 'queued'
  if(media==='failed'||media==='interrupted')return 'danger'
  const status=run.value?.status
  if(status==='running')return 'running'
  if(status==='queued')return run.value&&readyToStart(run.value)?'running':'queued'
  if(status==='completed')return 'success'
  if(status==='completed_with_errors')return 'warning'
  if(status==='failed'||status==='interrupted')return 'danger'
  return 'neutral'
})
const progress=computed(()=>{
  if(removal.value.deleting||removal.value.failed)return removal.value.percent
  if(transfer.value)return transfer.value.status==='waiting'?null:uploadPercent(transfer.value)
  const media=props.batch.media_preparation
  if(media?.state==='queued')return 0
  if(media?.state==='running')return media.progress_percent??null
  if(run.value?.status==='queued')return 0
  if(run.value?.status==='completed')return 100
  return run.value?.status==='running'||run.value?.status==='completed_with_errors'
    ?state.value.overallPercent??run.value.progress?.overall_percent??null
    :null
})
const stage=computed(()=>{
  if(removal.value.deleting||removal.value.failed)return removal.value.stage
  if(transfer.value){
    const row=transfer.value
    if(row.status==='waiting')return 'Ожидает передачи на сайт'
    if(row.status==='failed')return row.error||'Откройте очередь загрузок для повтора'
    const counts=row.recovery?'Докачка файла «'+row.name+'»':row.completed+' из '+row.totalFiles+' файлов'
    return row.status==='running'&&row.phase?counts+' · '+row.phase:counts
  }
  if(run.value?.status==='running'){
    const p=run.value.progress
    return p?.stage==='archive'
      ?'Подготовка архива · '+Math.round(p.stage_percent??0)+'%'
      :state.value.stageLabel
  }
  if(run.value?.status==='queued')return readyToStart(run.value)?state.value.detail:'Ожидает своей очереди'
  if(run.value?.status==='completed')return 'Обработка завершена'
  if(run.value?.status==='completed_with_errors')return 'Завершено с ошибками'
  return state.value.detail
})
</script>
<template>
<CompactTaskCard :number="position" :title="batch.display_name"
  :aria-label="'Фотоотчёт '+batch.display_name"
  :thumbnail-url="allowed('photos.media')?batch.cover_thumbnail_url:undefined"
  :status="removal.failed?'Ошибка удаления':removal.deleting?'Удаляется':transfer?uploadStatusLabel(transfer.status):state.label"
  :tone="statusTone" :progress="progress" :stage="stage" :indeterminate="removal.inProgress"
  :progress-motion-key="!transfer&&!removal.deleting&&!removal.failed&&run?.status==='running'?run.id:null"
  :progress-label="transfer?'Прогресс загрузки '+batch.display_name:undefined" :hide-time="!!transfer"
  :time-label="removal.deleting||removal.failed?undefined:timing.label"
  :time-detail="removal.deleting||removal.failed?undefined:timing.detail"
  :active="transfer?transfer.status==='running':(run?.status==='running'||batch.media_preparation?.state==='running')&&!removal.deleting&&!removal.failed">
  <template #meta>
    <span>{{batch.photos??0}} фото</span>
    <span v-if="batch.videos">{{batch.videos}} видео</span>
    <span v-if="batch.media_files">{{batch.media_files}} без сортировки</span>
    <span>{{bytes(batch.size_bytes)}}</span>
    <span v-if="run?.status==='queued'&&run.queue_position!=null&&!readyToStart(run)">№{{run.queue_position}} в очереди</span>
    <span v-if="run?.models?.megaloc?.groups!=null">{{run.models.megaloc.groups}} групп</span>
    <span v-else>{{date(batch.created_at)}}</span>
    <span v-if="run?.models?.megaloc?.uncertain!=null">Неопределено: {{run.models.megaloc.uncertain}}</span>
  </template>
  <template #actions>
    <button v-if="transfer" type="button" class="task-card-action" @click="emit('showUploads')">Ход загрузки</button>
    <button v-else-if="state.canStop&&run&&allowed('queue.stop')&&allowed('queue.view')" type="button" class="task-card-action"
      :disabled="busy" :title="run.status==='queued'?'Убрать из очереди':'Остановить обработку'"
      :aria-label="run.status==='queued'?'Убрать из очереди':'Остановить обработку'"
      @click="emit('stop',run.id)">■</button>
    <button v-else-if="state.canStart&&(batch.runs??0)===0&&allowed('photos.process')" type="button" class="task-card-action task-card-action-primary"
      :disabled="busy" @click="emit('start',batch.batch_id,batchThreshold(batch))">
      Обработать
    </button>
    <RouterLink v-else-if="state.resultId&&session.canResults" class="task-card-action task-card-action-primary"
      :to="'/results/'+state.resultId">Результат</RouterLink>
    <RouterLink v-else class="task-card-action" :to="'/fo/'+batch.batch_id">Открыть</RouterLink>
  </template>
  <template #menu>
    <RouterLink :to="'/fo/'+batch.batch_id">Открыть фотографии</RouterLink>
    <RouterLink v-if="run&&allowed('queue.detail')&&allowed('queue.view')" :to="'/queue/runs/'+run.id">Ход обработки</RouterLink>
    <RouterLink v-if="state.resultId&&session.canResults" :to="'/results/'+state.resultId">
      {{run?.id===state.resultId?'Открыть результаты':'Прошлые результаты'}}
    </RouterLink>
    <button v-if="allowed('photos.process')&&state.canStart&&!transfer&&(batch.runs??0)>0" type="button" :disabled="busy"
      @click="emit('start',batch.batch_id,batchThreshold(batch))">Повторить обработку</button>
    <button v-if="allowed('photos.auto')&&state.canCancelAuto&&!transfer" type="button" :disabled="busy"
      @click="emit('cancelAuto',batch.batch_id)">Отменить автозапуск</button>
  </template>
</CompactTaskCard>
</template>
