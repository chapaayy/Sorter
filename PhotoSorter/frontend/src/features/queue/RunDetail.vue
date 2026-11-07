<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {useRoute} from 'vue-router'
import {runApi} from '../../api/runs'
import {batchApi} from '../../api/batches'
import {usePolling} from '../../composables/usePolling'
import type {Run,Batch} from '../../types/api'
import {date,errorText,isActive,isComplete,runLabels} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import RunProgress from './RunProgress.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
const route=useRoute(),id=String(route.params.runId)
const run=ref<Run|null>(null),batch=ref<Batch|null>(null),busy=ref(false),error=ref(''),confirmStop=ref(false)
async function refresh(){
  try{
    run.value=await runApi.one(id)
    if(!batch.value&&run.value.batch_id)batch.value=await batchApi.one(run.value.batch_id)
    error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>{void refresh()})
usePolling(refresh,2200)
async function retryArchive(){
  busy.value=true
  try{await runApi.retryArchive(id);await refresh()}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function stop(){
  busy.value=true
  try{await runApi.stop(id);confirmStop.value=false;await refresh()}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="row" style="margin-bottom:22px"><RouterLink to="/queue?view=history" class="meta">← История очереди</RouterLink></div>
<PageHeader eyebrow="ОЧЕРЕДЬ / ПОДРОБНОСТИ" :title="batch?.display_name||'Запуск '+id" :subtitle="'MegaLoc · '+date(run?.started_at)+' · '+(run?runLabels[run.status]||run.status:'Загрузка…')">
  <template #actions>
    <UiButton v-if="run?.archive_state==='failed'&&['failed','interrupted'].includes(run.status)"
      :loading="busy" kind="primary" @click="retryArchive">Повторить подготовку ZIP</UiButton>
    <UiButton v-if="run&&(run.status==='queued'||run.status==='running')" kind="danger" :loading="busy" @click="confirmStop=true">{{run.status==='queued'?'Убрать из очереди':'Остановить'}}</UiButton>
    <RouterLink v-if="run&&!isActive(run.status)" :to="'/fo/'+run.batch_id" class="btn">Обработать повторно в ФО</RouterLink>
    <RouterLink v-if="run&&isComplete(run.status)" class="btn primary" :to="'/results/'+id">Результаты →</RouterLink>
  </template>
</PageHeader>
<div v-if="error" class="alert error">{{error}}</div>
<RunProgress v-if="run" :run="run"/>
<div v-if="run" class="panel stack" style="margin-top:20px">
  <h2>Параметры и действия</h2>
  <div class="grid3"><div><span class="label">Модель</span><strong>MegaLoc</strong></div><div><span class="label">Порог группировки</span><strong>{{run.grouping_threshold?.toFixed(2)||'0.50'}}</strong></div><div><span class="label">Идентификатор запуска</span><code class="meta">{{run.id}}</code></div></div>
  <div class="row wrap"><RouterLink :to="'/logs?run='+id" class="btn">Открыть журнал запуска</RouterLink><RouterLink :to="'/fo/'+run.batch_id" class="btn">Открыть партию ФО</RouterLink></div>
</div>
<ConfirmDialog v-if="confirmStop&&run"
  :title="run.status==='queued'?'Убрать из очереди MegaLoc?':'Остановить обработку MegaLoc?'"
  message="Текущий запуск будет остановлен. Оригиналы, история и предыдущие результаты сохранятся."
  :danger="true" :busy="busy" :confirm-label="run.status==='queued'?'Убрать из очереди':'Остановить'"
  @cancel="confirmStop=false" @confirm="stop"/>
</template>
