<script setup lang="ts">
import {computed} from 'vue'
import type {QueueTask} from '../../types/workQueue'
import type {TaskEstimate} from '../../utils/queueEstimates'
import {queueTime} from '../../utils/queueEstimates'
import {STATE_RU,hasBlockingFailure,isPrep} from '../../utils/queuePresentation'
import {date} from '../../utils/format'
import {deletionProgress} from '../../utils/deletionProgress'
import {useDeletionStore} from '../../stores/deletion'
import CompactTaskCard from '../../components/ui/CompactTaskCard.vue'

const props=defineProps<{task:QueueTask;position?:number;estimate?:TaskEstimate;busy?:boolean;starting?:boolean}>()
const emit=defineEmits<{
 (e:'action',task:QueueTask,kind:'stop'|'retry'|'skip'):void
 (e:'details',task:QueueTask):void
}>()
const deletion=useDeletionStore()
const removal=computed(()=>deletionProgress(props.task.batch_delete_state,props.task.batch_deletion_progress,
  !!props.task.batch_id&&deletion.pending(props.task.batch_id)))
const preparing=computed(()=>isPrep(props.task))
const media=computed(()=>props.task.kind==='media_preparation')
const canStop=computed(()=>!media.value&&(props.task.state==='running'||props.task.state==='queued'))
const progress=computed<number|null>(()=>{
  if(removal.value.deleting||removal.value.failed)return removal.value.percent
  const task=props.task
  if(task.state==='completed')return 100
  if(task.state==='queued')return 0
  if(preparing.value||media.value){
    return task.total_count&&task.total_count>0
      ?Math.round(100*(task.completed_count||0)/task.total_count):null
  }
  const overall=task.fo_progress?.overall_percent
  return typeof overall==='number'&&Number.isFinite(overall)?overall:null
})
const stage=computed(()=>{
  if(removal.value.deleting||removal.value.failed)return removal.value.stage
  if(media.value){
    const task=props.task
    if(task.state==='queued')return 'Перекодирование файлов · в очереди'
    if(task.state==='running')return 'Перекодирование файлов · '+(task.completed_count??0)+' из '+task.total_count
    return task.error||'Перекодирование файлов завершено'
  }
  if(hasBlockingFailure(props.task))return 'Ожидает повторения или пропуска'
  if(props.task.state==='queued')return props.starting?'Подготовка к запуску MegaLoc':'Ожидает предыдущие задачи'
  if(props.task.state==='running'){
    if(props.task.stop_requested)return 'Запрошена остановка'
    if(preparing.value)return 'MegaLoc · подготовка образцов'
    const p=props.task.fo_progress
    return p?.stage==='archive'
      ?'Подготовка архива · '+Math.round(p.stage_percent??0)+'%'
      :p?.stage_label||'MegaLoc · вычисление'
  }
  if(props.task.state==='completed')return 'Обработка завершена'
  return props.task.error||STATE_RU[props.task.state]
})
const tone=computed(()=>{
  if(removal.value.deleting)return 'deleting'
  if(removal.value.failed)return 'danger'
  if(hasBlockingFailure(props.task)||props.task.state==='failed')return 'danger'
  if(props.task.state==='completed')return 'success'
  if(props.task.state==='completed_with_errors')return 'warning'
  if(props.task.state==='running')return 'running'
  if(props.task.state==='queued')return props.starting?'running':'queued'
  return 'neutral'
})
const time=computed(()=>queueTime(props.task,props.estimate))
const count=computed(()=>preparing.value||media.value?props.task.total_count:props.task.fo_photo_count)
</script>
<template>
<CompactTaskCard :number="position??task.seq" class="queue-task-row"
  :title="preparing?'Подготовка образцов':media?'Перекодирование файлов':task.batch_name||'Фотоотчёт'"
  :thumbnail-url="preparing?null:task.fo_thumbnail_url"
  :icon="preparing?'references':'photos'"
  :status="removal.deleting?'Удаляется':removal.failed?'Ошибка удаления':task.stop_requested&&task.state==='running'?'Остановка':starting?'Запуск обработки':STATE_RU[task.state]"
  :tone="tone" :progress="progress" :stage="stage" :indeterminate="removal.inProgress"
  :progress-motion-key="task.state==='running'&&!task.stop_requested&&!removal.deleting&&!removal.failed?String(task.seq):null"
  :time-label="removal.deleting||removal.failed?undefined:time.label"
  :time-detail="removal.deleting||removal.failed?undefined:time.detail"
  :active="task.state==='running'&&!removal.deleting&&!removal.failed">
  <template #meta>
    <span>{{preparing?'Образцы':media?task.batch_name:'ФО'}}</span>
    <span v-if="count!=null">{{count}} {{media?"файлов":"фото"}}</span>
    <span v-if="preparing&&task.failed_count">Ошибок: {{task.failed_count}}</span>
    <span v-if="task.state!=='queued'&&task.state!=='running'">{{date(task.created_at)}}</span>
  </template>
  <template #actions>
    <button v-if="task.state==='running'&&canStop" type="button" class="task-card-action"
      :disabled="busy||!!task.stop_requested" aria-label="Остановить задачу"
      title="Остановить задачу" @click="emit('action',task,'stop')">■</button>
    <button v-if="preparing" type="button" class="task-card-action"
      @click="emit('details',task)">Подробности</button>
    <RouterLink v-else-if="media&&task.batch_id" :to="'/fo/'+task.batch_id" class="task-card-action">Открыть ФО</RouterLink>
    <RouterLink v-else-if="task.fo_run_id" :to="'/queue/runs/'+task.fo_run_id"
      class="task-card-action">Обработка</RouterLink>
  </template>
  <template #menu>
    <button v-if="preparing" type="button" @click="emit('details',task)">Открыть подробности</button>
    <RouterLink v-else-if="media&&task.batch_id" :to="'/fo/'+task.batch_id" class="task-card-action">Открыть ФО</RouterLink>
    <RouterLink v-else-if="task.fo_run_id" :to="'/queue/runs/'+task.fo_run_id">Ход обработки</RouterLink>
    <button v-if="hasBlockingFailure(task)" type="button" :disabled="busy"
      @click="emit('action',task,'retry')">Повторить подготовку</button>
    <button v-if="preparing&&hasBlockingFailure(task)" type="button" class="is-danger"
      :disabled="busy" @click="emit('action',task,'skip')">Пропустить обновление</button>
    <button v-if="task.state==='queued'&&canStop" type="button" class="is-danger"
      :disabled="busy" @click="emit('action',task,preparing?'skip':'stop')">Убрать из очереди</button>
  </template>
</CompactTaskCard>
</template>
