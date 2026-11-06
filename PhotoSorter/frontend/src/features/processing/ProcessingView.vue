<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {runApi} from '../../api/runs'
import {systemApi} from '../../api/system'
import {usePolling} from '../../composables/usePolling'
import {errorText} from '../../utils/format'
import {activeInference,orderedQueue} from '../../utils/processingDashboard'
import type {Batch,Run,ModelInfo,ProcessingSettings,SystemStatus} from '../../types/api'
import {useNoticeStore} from '../../stores/notice'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
import RunProgress from './RunProgress.vue'
import ProcessingOverview from './ProcessingOverview.vue'
import ProcessingQueue from './ProcessingQueue.vue'
import ProcessingHistory from './ProcessingHistory.vue'

const notice=useNoticeStore()
const activeJobs=ref<Run[]>([]),history=ref<Run[]>([])
const historyTotal=ref(0),busyMore=ref(false),busyStop=ref(''),downloading=ref(false)
const model=ref<ModelInfo|null>(null),settings=ref<ProcessingSettings|null>(null)
const system=ref<SystemStatus|null>(null),batches=ref<Batch[]>([])
const liveError=ref(''),infoError=ref(''),historyError=ref('')
const stopTarget=ref<Run|null>(null)
const PAGE=30

const queue=computed(()=>orderedQueue(activeJobs.value))
const current=computed(()=>activeInference(activeJobs.value))
const names=computed(()=>Object.fromEntries(batches.value.map(b=>[b.batch_id,b.display_name])))
const queueTotal=computed(()=>system.value?.worker.queue.queued??queue.value.length)

async function refreshLive(){
  try{
    const [jobs,status]=await Promise.all([runApi.active(),systemApi.status()])
    activeJobs.value=jobs.runs
    system.value=status
    liveError.value=''
  }catch(e){liveError.value=errorText(e)}
}
async function refreshHistory(){
  try{
    const page=await runApi.history(PAGE)
    const latest=page.runs
    const ids=new Set(latest.map(run=>run.id))
    history.value=[...latest,...history.value.slice(PAGE).filter(run=>!ids.has(run.id))]
    historyTotal.value=page.total
    historyError.value=''
  }catch(e){historyError.value=errorText(e)}
}
async function refreshInfo(){
  try{
    const [m,s,b]=await Promise.all([runApi.models(),runApi.autoSettings(),batchApi.list(200)])
    model.value=m
    settings.value=s
    batches.value=b.batches
    infoError.value=''
  }catch(e){infoError.value=errorText(e)}
}
async function loadMore(){
  if(busyMore.value||history.value.length>=historyTotal.value)return
  busyMore.value=true
  try{
    const page=await runApi.history(PAGE,history.value.length)
    const known=new Set(history.value.map(run=>run.id))
    history.value.push(...page.runs.filter(run=>!known.has(run.id)))
    historyTotal.value=page.total
    historyError.value=''
  }catch(e){historyError.value=errorText(e)}
  finally{busyMore.value=false}
}

onMounted(()=>{
  void refreshLive()
  void refreshHistory()
  void refreshInfo()
})
// Lightweight live state only. History and model/settings change less often.
usePolling(refreshLive,4000)
usePolling(refreshHistory,15000)
usePolling(refreshInfo,45000)

async function stop(){
  const job=stopTarget.value
  if(!job||busyStop.value)return
  busyStop.value=job.id
  try{
    await runApi.stop(job.id)
    stopTarget.value=null
    notice.add(job.status==='queued'?'Задание снято с очереди':'Запрошена остановка обработки','ok')
    await Promise.all([refreshLive(),refreshHistory()])
  }catch(e){
    liveError.value=errorText(e)
    await refreshLive()
    await refreshHistory()
  }finally{busyStop.value=''}
}
async function install(){
  if(downloading.value)return
  downloading.value=true
  try{
    await runApi.downloadModel()
    notice.add('Загрузка модели MegaLoc запущена','ok')
    await refreshInfo()
  }catch(e){infoError.value=errorText(e)}
  finally{downloading.value=false}
}
</script>

<template>
<PageHeader eyebrow="НЕЙРОСЕТЕВАЯ ОБРАБОТКА" title="Обработка"
  subtitle="Панель MegaLoc: состояние Worker, текущая обработка, очередь и история. Запуск новых партий — в «ФО».">
  <template #actions>
    <RouterLink to="/fo" class="btn primary">Открыть фотоотчёты</RouterLink>
  </template>
</PageHeader>

<div v-if="liveError" class="alert error" role="alert" style="margin-bottom:14px">
  Не удалось обновить состояние очереди: {{liveError}}
</div>
<div v-if="infoError" class="alert error" role="alert" style="margin-bottom:14px">
  Не удалось обновить информацию о модели и настройках: {{infoError}}
</div>

<div class="stack gap24">
  <ProcessingOverview :model="model" :settings="settings" :system="system"
    :downloading="downloading" @install="install"/>

  <section class="stack" aria-label="Текущее активное задание">
    <div class="row between wrap">
      <h2 style="margin:0">Текущее задание</h2>
      <span class="meta">MegaLoc выполняет только одну обработку одновременно</span>
    </div>
    <template v-if="current">
      <div class="row between wrap">
        <RouterLink class="processing-current-link" :to="'/fo/'+current.batch_id">
          {{names[current.batch_id]||current.batch_id}}
        </RouterLink>
        <div class="row wrap">
          <RouterLink :to="'/processing/'+current.id" class="btn small">Подробности</RouterLink>
          <UiButton v-if="current.status==='running'" kind="danger" small
            :loading="busyStop===current.id" @click="stopTarget=current">Остановить</UiButton>
        </div>
      </div>
      <RunProgress :run="current"/>
    </template>
    <section v-else class="panel processing-idle">
      <strong>Сейчас MegaLoc не обрабатывает фотографии</strong>
      <p class="meta">Если задания ожидают, Worker возьмёт их по очереди. Для создания нового запуска откройте «ФО».</p>
    </section>
  </section>

  <ProcessingQueue :runs="queue" :names="names" :total="queueTotal"
    :busy-id="busyStop" @stop="stopTarget=$event"/>

  <div v-if="historyError" class="alert error" role="alert">
    Не удалось обновить историю запусков: {{historyError}}
  </div>
  <ProcessingHistory :runs="history" :names="names" :total="historyTotal"
    :loading-more="busyMore" @more="loadMore"/>
</div>

<ConfirmDialog v-if="stopTarget"
  :title="stopTarget.status==='queued'?'Убрать задание из очереди?':'Остановить обработку MegaLoc?'"
  :message="'Партия «'+(names[stopTarget.batch_id]||stopTarget.batch_id)+'». Фотографии, предыдущие запуски и результаты сохранятся.'"
  :confirm-label="stopTarget.status==='queued'?'Убрать из очереди':'Остановить'"
  :danger="true" :busy="!!busyStop"
  @cancel="stopTarget=null" @confirm="stop"/>
</template>
