<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {useRouter} from 'vue-router'
import {batchApi} from '../../api/batches'
import {canProcessBatch} from '../../utils/batches'
import {runApi} from '../../api/runs'
import type {Batch,Run,ModelInfo} from '../../types/api'
import {usePolling} from '../../composables/usePolling'
import {date,errorText,isActive,runLabels,bytes} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import UiSelect from '../../components/ui/UiSelect.vue'
import RowCard from '../../components/ui/RowCard.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import RunProgress from './RunProgress.vue'
import {useNoticeStore} from '../../stores/notice'
const router=useRouter(),notice=useNoticeStore()
const batches=ref<Batch[]>([]),runs=ref<Run[]>([]),model=ref<ModelInfo|null>(null),chosen=ref(''),threshold=ref(.50)
const submitting=ref(false),downloading=ref(false),error=ref(''),search=ref('')
const activeRuns=computed(()=>runs.value.filter(r=>isActive(r.status)))
const latest=computed(()=>activeRuns.value[0]||runs.value[0])
const history=computed(()=>runs.value.filter(r=>(r.id+' '+(batchName(r.batch_id))).toLowerCase().includes(search.value.toLowerCase())))
const selectable=computed(()=>batches.value.filter(b=>b.delete_state==='active'&&(b.photos??0)>0))
const available=computed(()=>batches.value.filter(canProcessBatch))
const selectedBatch=computed(()=>selectable.value.find(b=>b.batch_id===chosen.value))
const selectedReady=computed(()=>!!selectedBatch.value&&canProcessBatch(selectedBatch.value))
function batchName(id:string){return batches.value.find(b=>b.batch_id===id)?.display_name||id}
async function load(){
  try{
    const [rs,bs,m]=await Promise.all([runApi.list(),batchApi.list(200),runApi.models()])
    runs.value=rs.runs;batches.value=bs.batches;model.value=m
    if(!selectable.value.some(b=>b.batch_id===chosen.value))chosen.value=selectable.value[0]?.batch_id||''
    error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>{void load()})
usePolling(load,3000)
async function start(){
  if(!selectedReady.value||submitting.value)return
  submitting.value=true;error.value=''
  try{
    const created=await runApi.start(chosen.value,threshold.value)
    notice.add('Запуск добавлен в очередь MegaLoc','ok')
    await load()
    await router.push('/processing/'+created.id)
  }catch(e){error.value=errorText(e)}finally{submitting.value=false}
}
async function stop(id:string){
  try{await runApi.stop(id);notice.add('Остановка запрошена','ok');await load()}
  catch(e){error.value=errorText(e)}
}
async function install(){
  downloading.value=true
  try{await runApi.downloadModel();notice.add('Загрузка MegaLoc запущена');await load()}
  catch(e){error.value=errorText(e)}finally{downloading.value=false}
}
</script>
<template>
<PageHeader eyebrow="НЕЙРОСЕТЕВАЯ ОБРАБОТКА" title="Обработка" subtitle="Сначала MegaLoc группирует ФО, затем сопоставляет группы с библиотекой SAM."/>
<div v-if="error" class="alert error" role="alert" style="margin-bottom:20px">{{error}}</div>
<section class="panel stack" style="margin-bottom:20px">
  <div class="panel-header"><h2>Новый запуск</h2><span class="status">Доступна одна модель · MegaLoc</span></div>
  <div class="grid3">
    <div class="field"><span class="label">Партия ФО</span><UiSelect v-model="chosen" label="Партия ФО" placeholder="Выберите партию" :disabled="!selectable.length" :options="selectable.map(b=>({value:b.batch_id,label:b.display_name+' · '+b.photos+' ФО'+((b.pending??0)>0?' · '+b.pending+' незавершённых':'')}))"/></div>
    <div class="field"><span class="label">Модель</span><div class="readonly-field" aria-label="Модель">MegaLoc · CPU</div></div>
    <label class="field"><span class="label">Порог группировки: {{threshold.toFixed(2)}}</span><input v-model.number="threshold" type="range" min=".50" max=".99" step=".01" aria-label="Порог группировки"/></label>
  </div>
  <p v-if="!selectable.length" class="meta">Нет партий с фотографиями. Загрузите ФО во вкладке «Фотоотчёты».</p>
  <div v-if="selectedBatch&&(selectedBatch.pending??0)>0" class="alert warning">
    {{selectedBatch.photos}} фотографий готовы, но {{selectedBatch.pending}} файлов ещё не завершены.
    <RouterLink :to="'/fo/'+selectedBatch.batch_id">Откройте партию</RouterLink>,
    чтобы докачать их, завершить сохранение или отменить незавершённые передачи.
  </div>
  <div class="row between wrap">
    <span class="meta">{{model?.models[0]?.available?'Модель готова. Запуски выполняются по одному.':model?.models[0]?.reason||'Проверка состояния модели…'}}</span>
    <div class="row">
      <UiButton v-if="model&&!model.models[0]?.available" :loading="downloading" @click="install">Установить MegaLoc</UiButton>
      <UiButton kind="primary" :loading="submitting" :disabled="!model?.models[0]?.available||!selectedReady" @click="start">▶ Запустить / поставить в очередь</UiButton>
    </div>
  </div>
</section>
<RunProgress v-if="latest" :run="latest" style="margin-bottom:22px"/>
<div v-if="latest&&isActive(latest.status)" class="row between" style="margin:0 0 28px"><RouterLink :to="'/processing/'+latest.id" class="meta">Подробности запуска →</RouterLink><UiButton kind="danger" @click="stop(latest.id)">Остановить</UiButton></div>
<div class="row between wrap" style="margin-bottom:16px"><h2 style="margin:0">История обработок</h2><input v-model="search" placeholder="Поиск запусков…" aria-label="Поиск запусков" style="max-width:300px"/></div>
<div v-if="history.length" class="stack">
  <RowCard v-for="r in history" :key="r.id" icon="◉" :to="'/processing/'+r.id">
    <template #title>{{batchName(r.batch_id)}}</template>
    <template #subtitle>{{date(r.started_at)}} · MegaLoc</template>
    <template #status>{{runLabels[r.status]||r.status}}<span v-if="r.queue_position"> · очередь №{{r.queue_position}}</span></template>
    <template #metrics><div class="metric"><strong>{{r.progress?.total??'—'}}</strong><small>ед. на этапе</small></div><div class="metric"><strong>{{r.grouping_threshold?.toFixed(2)||'0.50'}}</strong><small>порог</small></div></template>
  </RowCard>
</div>
<EmptyState v-else title="Нет запусков" detail="Выберите партию с фотографиями, чтобы запустить первую сортировку." icon="◉"/>
</template>
