<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {runApi} from '../../api/runs'
import {usePolling} from '../../composables/usePolling'
import {errorText} from '../../utils/format'
import type {Batch} from '../../types/api'
import type {QueueTask} from '../../types/workQueue'
import {workQueueApi} from '../../api/workQueue'
import {estimateQueue} from '../../utils/queueEstimates'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {useNoticeStore} from '../../stores/notice'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
import FoBatchCard from './FoBatchCard.vue'

const notice=useNoticeStore(),uploader=useUploadCenterStore()
const batches=ref<Batch[]>([]),search=ref('')
const queueTasks=ref<QueueTask[]>([]),queueHistory=ref<QueueTask[]>([])
const clock=ref(Date.now())
const estimates=computed(()=>estimateQueue(queueTasks.value,queueHistory.value,clock.value))
function runEstimate(id?:string){
  if(!id)return undefined
  const row=queueTasks.value.find(t=>t.fo_run_id===id)
  return row?estimates.value.get(row.seq):undefined
}
async function refreshQueue(){
  try{
    const [active,history]=await Promise.all([
      workQueueApi.list('active',200),workQueueApi.list('history',100)
    ])
    queueTasks.value=active.tasks
    queueHistory.value=history.tasks
    clock.value=Date.now()
  }catch{/* FO list remains available if the queue service is temporarily unavailable. */}
}
const loading=ref(true),loadingMore=ref(false),error=ref('')
const total=ref(0),activeAction=ref(''),stopConfirm=ref<{id:string;name:string;queued:boolean}|null>(null)
let refreshing=false
const filtered=computed(()=>batches.value.filter(b=>
  b.delete_state!=='deleted'&&b.display_name.toLowerCase().includes(search.value.toLowerCase())))

async function load(more=false){
  if(more&&loadingMore.value)return
  if(more)loadingMore.value=true
  else if(!batches.value.length)loading.value=true
  try{
    const data=await batchApi.list(100,more?batches.value.length:0)
    batches.value=more?[...batches.value,...data.batches]:data.batches
    total.value=data.total;error.value=''
  }catch(e){error.value=errorText(e)}
  finally{loading.value=false;loadingMore.value=false}
}
/** Poll all visible pages, never drop previously loaded rows on refresh. */
async function refreshVisible(){
  if(refreshing)return
  refreshing=true
  try{
    const target=Math.max(100,batches.value.length)
    const next:Batch[]=[]
    let newTotal=total.value
    for(let offset=0;offset<target;offset+=200){
      const data=await batchApi.list(Math.min(200,target-offset),offset)
      next.push(...data.batches)
      newTotal=data.total
      if(next.length>=newTotal)break
    }
    batches.value=next;total.value=newTotal;error.value=''
  }catch(e){error.value=errorText(e)}
  finally{refreshing=false}
}
onMounted(()=>{void load();void refreshQueue()})
usePolling(refreshVisible,4000)
usePolling(refreshQueue,6000)

async function start(batchId:string,threshold:number){
  if(activeAction.value)return
  activeAction.value=batchId;error.value=''
  try{
    await runApi.start(batchId,threshold)
    notice.add('MegaLoc поставлен в очередь','ok')
    await Promise.all([refreshVisible(),refreshQueue()])
  }catch(e){error.value=errorText(e);await refreshVisible()}
  finally{activeAction.value=''}
}
async function cancelAuto(batchId:string){
  if(activeAction.value)return
  activeAction.value=batchId;error.value=''
  try{
    await batchApi.cancelAutomatic(batchId)
    notice.add('Ожидавший автозапуск отменён','ok')
    await refreshVisible()
  }catch(e){error.value=errorText(e)}
  finally{activeAction.value=''}
}
function confirmStop(runId:string){
  const batch=batches.value.find(b=>b.latest_run?.id===runId)
  if(!batch)return
  stopConfirm.value={id:runId,name:batch.display_name,queued:batch.latest_run?.status==='queued'}
}
async function stop(){
  const request=stopConfirm.value
  if(!request||activeAction.value)return
  activeAction.value=request.id;error.value=''
  try{
    await runApi.stop(request.id)
    stopConfirm.value=null
    notice.add(request.queued?'Задание убрано из очереди':'Запрошена остановка обработки','ok')
    await Promise.all([refreshVisible(),refreshQueue()])
  }catch(e){error.value=errorText(e);await refreshVisible()}
  finally{activeAction.value=''}
}
</script>
<template>
<PageHeader eyebrow="БИБЛИОТЕКА ФО" title="Фотоотчёты"
  subtitle="Состояние загрузки и MegaLoc для каждой партии, управление обработкой и результаты.">
  <template #actions>
    <UiButton kind="primary" @click="uploader.launch('fo')">+ Загрузить папку</UiButton>
  </template>
</PageHeader>
<div class="toolbar">
  <input v-model="search" class="search" placeholder="Поиск по названию партии…" aria-label="Поиск фотоотчётов"/>
  <span class="meta">Партий: {{total}}</span>
  <UiButton small @click="refreshVisible">Обновить</UiButton>
</div>
<div v-if="error" class="alert error" role="alert" style="margin-bottom:16px">{{error}}</div>
<div v-if="filtered.length" class="stack">
  <FoBatchCard v-for="(batch,index) in filtered" :key="batch.batch_id" :batch="batch"
    :position="index+1" :estimate="runEstimate(batch.latest_run?.id)"
    :busy="activeAction===batch.batch_id||activeAction===batch.latest_run?.id"
    @start="start" @stop="confirmStop" @cancel-auto="cancelAuto"/>
  <div v-if="batches.length<total" class="pagination">
    <UiButton :loading="loadingMore" @click="load(true)">Показать ещё</UiButton>
  </div>
</div>
<EmptyState v-else-if="!loading" title="Пока нет фотоотчётов"
  detail="Выберите папку, чтобы загрузить фотографии первой партии." icon="▤">
  <UiButton kind="primary" @click="uploader.launch('fo')">Загрузить папку</UiButton>
</EmptyState>
<div v-else class="meta">Загружаем список партий…</div>
<ConfirmDialog v-if="stopConfirm" :title="stopConfirm.queued?'Убрать из очереди MegaLoc?':'Остановить обработку MegaLoc?'"
  :message="'Партия «'+stopConfirm.name+'». История предыдущих запусков и фотографии сохранятся.'"
  :confirm-label="stopConfirm.queued?'Убрать из очереди':'Остановить'"
  :danger="true" :busy="!!activeAction" @cancel="stopConfirm=null" @confirm="stop"/>
</template>
