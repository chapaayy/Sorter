<script setup lang="ts">
import {onMounted,ref,computed} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {runApi} from '../../api/runs'
import {batchApi} from '../../api/batches'
import {usePolling} from '../../composables/usePolling'
import type {Run,Batch} from '../../types/api'
import {date,errorText,isActive,isComplete,runLabels} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import RunProgress from './RunProgress.vue'
const route=useRoute(),router=useRouter(),id=String(route.params.runId)
const run=ref<Run|null>(null),batch=ref<Batch|null>(null),busy=ref(false),error=ref('')
async function refresh(){
  try{
    run.value=await runApi.one(id)
    if(!batch.value&&run.value.batch_id)batch.value=await batchApi.one(run.value.batch_id)
    error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>{void refresh()})
usePolling(refresh,2200)
async function stop(){
  busy.value=true
  try{await runApi.stop(id);await refresh()}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function repeat(){
  if(!run.value)return
  busy.value=true
  try{const created=await runApi.start(run.value.batch_id,run.value.grouping_threshold||.5);await router.replace('/processing/'+created.id)}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="row" style="margin-bottom:22px"><RouterLink to="/processing" class="meta">← История обработок</RouterLink></div>
<PageHeader eyebrow="ОБРАБОТКА / ПОДРОБНОСТИ" :title="batch?.display_name||'Запуск '+id" :subtitle="'MegaLoc · '+date(run?.started_at)+' · '+(run?runLabels[run.status]||run.status:'Загрузка…')">
  <template #actions><UiButton v-if="run&&isActive(run.status)" kind="danger" :loading="busy" @click="stop">Остановить</UiButton>
    <UiButton v-if="run&&!isActive(run.status)" :loading="busy" @click="repeat">Повторить обработку</UiButton>
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
</template>
