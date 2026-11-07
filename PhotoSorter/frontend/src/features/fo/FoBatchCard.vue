<script setup lang="ts">
import {computed} from 'vue'
import type {Batch} from '../../types/api'
import type {TaskEstimate} from '../../utils/queueEstimates'
import {runTime} from '../../utils/queueEstimates'
import {batchProcessing,batchThreshold} from '../../utils/batchProcessing'
import {bytes,date} from '../../utils/format'
import CompactTaskCard from '../../components/ui/CompactTaskCard.vue'

const props=defineProps<{batch:Batch;position:number;estimate?:TaskEstimate;busy?:boolean}>()
const emit=defineEmits<{
  (e:'start',batchId:string,threshold:number):void
  (e:'stop',runId:string):void
  (e:'cancelAuto',batchId:string):void
}>()
const state=computed(()=>batchProcessing(props.batch))
const run=computed(()=>state.value.run)
const timing=computed(()=>runTime(run.value,props.estimate))
const statusTone=computed(()=>{
  const status=run.value?.status
  if(status==='running')return 'running'
  if(status==='queued')return 'queued'
  if(status==='completed')return 'success'
  if(status==='completed_with_errors')return 'warning'
  if(status==='failed'||status==='interrupted')return 'danger'
  return 'neutral'
})
const progress=computed(()=>{
  if(run.value?.status==='queued')return 0
  if(run.value?.status==='completed')return 100
  return run.value?.status==='running'||run.value?.status==='completed_with_errors'
    ?state.value.overallPercent??run.value.progress?.overall_percent??null
    :null
})
const stage=computed(()=>{
  if(run.value?.status==='running'){
    const p=run.value.progress
    return p?.stage==='archive'
      ?'Подготовка архива · '+Math.round(p.stage_percent??0)+'%'
      :state.value.stageLabel
  }
  if(run.value?.status==='queued')return 'Ожидает своей очереди'
  if(run.value?.status==='completed')return 'Обработка завершена'
  if(run.value?.status==='completed_with_errors')return 'Завершено с ошибками'
  return state.value.detail
})
</script>
<template>
<CompactTaskCard :number="position" :title="batch.display_name"
  :aria-label="'Фотоотчёт '+batch.display_name"
  :thumbnail-url="batch.cover_thumbnail_url" :status="state.label"
  :tone="statusTone" :progress="progress" :stage="stage"
  :time-label="timing.label" :time-detail="timing.detail"
  :active="run?.status==='running'">
  <template #meta>
    <span>{{batch.photos??0}} фото</span>
    <span>{{bytes(batch.size_bytes)}}</span>
    <span v-if="run?.status==='queued'&&run.queue_position!=null">№{{run.queue_position}} в очереди</span>
    <span v-if="run?.models?.megaloc?.groups!=null">{{run.models.megaloc.groups}} групп</span>
    <span v-else>{{date(batch.created_at)}}</span>
    <span v-if="run?.models?.megaloc?.uncertain!=null">Неопределено: {{run.models.megaloc.uncertain}}</span>
  </template>
  <template #actions>
    <button v-if="state.canStop&&run" type="button" class="task-card-action"
      :disabled="busy" :title="run.status==='queued'?'Убрать из очереди':'Остановить обработку'"
      :aria-label="run.status==='queued'?'Убрать из очереди':'Остановить обработку'"
      @click="emit('stop',run.id)">■</button>
    <button v-else-if="state.canStart" type="button" class="task-card-action task-card-action-primary"
      :disabled="busy" @click="emit('start',batch.batch_id,batchThreshold(batch))">
      {{(batch.runs??0)>0?'Повторить':'Обработать'}}
    </button>
    <RouterLink v-else-if="state.resultId" class="task-card-action task-card-action-primary"
      :to="'/results/'+state.resultId">Результат</RouterLink>
    <RouterLink v-else class="task-card-action" :to="'/fo/'+batch.batch_id">Открыть</RouterLink>
  </template>
  <template #menu>
    <RouterLink :to="'/fo/'+batch.batch_id">Открыть фотографии</RouterLink>
    <RouterLink v-if="run" :to="'/queue/runs/'+run.id">Ход обработки</RouterLink>
    <RouterLink v-if="state.resultId" :to="'/results/'+state.resultId">
      {{run?.id===state.resultId?'Открыть результаты':'Прошлые результаты'}}
    </RouterLink>
    <button v-if="state.canCancelAuto" type="button" :disabled="busy"
      @click="emit('cancelAuto',batch.batch_id)">Отменить автозапуск</button>
  </template>
</CompactTaskCard>
</template>
