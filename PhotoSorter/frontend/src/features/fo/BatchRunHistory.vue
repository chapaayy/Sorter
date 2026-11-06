<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {usePolling} from '../../composables/usePolling'
import type {Run} from '../../types/api'
import {date,runLabels,isActive,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
const props=defineProps<{batchId:string}>()
const runs=ref<Run[]>([]),total=ref(0),busy=ref(false),error=ref('')
const PAGE=20
async function reload(){
  try{
    const data=await batchApi.runs(props.batchId,PAGE,0)
    const first=data.runs
    const ids=new Set(first.map(r=>r.id))
    runs.value=[...first,...runs.value.slice(PAGE).filter(r=>!ids.has(r.id))]
    total.value=data.total;error.value=''
  }catch(e){error.value=errorText(e)}
}
async function more(){
  if(busy.value||runs.value.length>=total.value)return
  busy.value=true
  try{
    const data=await batchApi.runs(props.batchId,PAGE,runs.value.length)
    const known=new Set(runs.value.map(r=>r.id))
    runs.value.push(...data.runs.filter(r=>!known.has(r.id)))
    total.value=data.total;error.value=''
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
onMounted(()=>{void reload()})
usePolling(async()=>{if(runs.value.some(r=>isActive(r.status)))await reload()},3500)
</script>
<template>
<section class="panel stack" aria-label="История обработок партии">
  <div class="row between wrap"><h2 style="margin:0">История запусков MegaLoc</h2><UiButton small @click="reload">Обновить</UiButton></div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <div v-if="!runs.length" class="meta">Для этой партии пока нет запусков.</div>
  <div v-for="run in runs" :key="run.id" class="fo-history-row">
    <div class="fo-history-main">
      <strong>{{runLabels[run.status]||run.status}}</strong>
      <span class="meta">{{date(run.actual_started_at||run.created_at||run.started_at)}} · порог {{run.grouping_threshold?.toFixed(2)??'0.50'}} · {{run.source==='automatic'?'автоматически':'вручную'}}</span>
      <span v-if="run.status==='queued'&&run.queue_position" class="meta">Очередь №{{run.queue_position}}</span>
    </div>
    <div class="row wrap">
      <RouterLink :to="'/processing/'+run.id" class="btn small">Подробности</RouterLink>
      <RouterLink v-if="['completed','completed_with_errors'].includes(run.status)" :to="'/results/'+run.id" class="btn small">Результаты</RouterLink>
    </div>
  </div>
  <div v-if="runs.length<total" class="pagination">
    <UiButton small :loading="busy" @click="more">Показать ещё ({{total-runs.length}})</UiButton>
  </div>
</section>
</template>
