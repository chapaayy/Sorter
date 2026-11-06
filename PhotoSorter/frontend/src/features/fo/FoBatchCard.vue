<script setup lang="ts">
import {computed} from 'vue'
import type {Batch} from '../../types/api'
import {batchProcessing,batchThreshold} from '../../utils/batchProcessing'
import {date,bytes} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import BatchProcessingStatus from './BatchProcessingStatus.vue'

const props=defineProps<{batch:Batch;busy?:boolean}>()
const emit=defineEmits<{
  (e:'start',batchId:string,threshold:number):void
  (e:'stop',runId:string):void
  (e:'cancelAuto',batchId:string):void
}>()
const state=computed(()=>batchProcessing(props.batch))
const activeRun=computed(()=>state.value.run)
</script>
<template>
<article class="panel fo-batch-card" :aria-label="'Фотоотчёт '+batch.display_name">
  <div class="fo-batch-main">
    <div class="fo-batch-heading">
      <RouterLink :to="'/fo/'+batch.batch_id" class="fo-batch-title" :title="batch.display_name">{{batch.display_name}}</RouterLink>
      <span class="meta">{{date(batch.created_at)}}</span>
    </div>
    <div class="fo-batch-stats">
      <span><strong>{{batch.photos??'—'}}</strong> ФО</span>
      <span>{{bytes(batch.size_bytes)}}</span>
      <span v-if="batch.upload_manifest_state==='waiting'||(batch.pending??0)>0" class="meta">Нужна докачка</span>
    </div>
  </div>
  <BatchProcessingStatus :batch="batch" compact/>
  <div class="fo-batch-actions">
    <RouterLink :to="'/fo/'+batch.batch_id" class="btn small">Открыть ФО</RouterLink>
    <RouterLink v-if="activeRun" :to="'/processing/'+activeRun.id" class="btn small">Подробности</RouterLink>
    <RouterLink v-if="state.resultId" :to="'/results/'+state.resultId" class="btn small">
      {{activeRun?.id===state.resultId?'Результаты':'Прошлые результаты'}}
    </RouterLink>
    <UiButton v-if="state.canStart" small kind="primary" :loading="busy" @click="emit('start',batch.batch_id,batchThreshold(batch))">
      {{(batch.runs??0)>0?'Повторить обработку':'Обработать'}}
    </UiButton>
    <UiButton v-if="state.canCancelAuto" small :loading="busy" @click="emit('cancelAuto',batch.batch_id)">Отменить автозапуск</UiButton>
    <UiButton v-if="state.canStop&&activeRun" small kind="danger" :loading="busy" @click="emit('stop',activeRun.id)">
      {{activeRun.status==='queued'?'Убрать из очереди':'Остановить'}}
    </UiButton>
  </div>
</article>
</template>
