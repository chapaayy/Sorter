<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {workQueueApi} from '../../api/workQueue'
import {runApi} from '../../api/runs'
import {usePolling} from '../../composables/usePolling'
import {useNoticeStore} from '../../stores/notice'
import {errorText} from '../../utils/format'
import type {QueueTask} from '../../types/workQueue'
import {hasBlockingFailure} from '../../utils/queuePresentation'
import {estimateQueue} from '../../utils/queueEstimates'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
import QueueTaskRow from './QueueTaskRow.vue'
import QueueTaskDetail from './QueueTaskDetail.vue'

const notice=useNoticeStore()
const tasks=ref<QueueTask[]>([]),history=ref<QueueTask[]>([]),historyTotal=ref(0)
const activeTotal=ref(0),busy=ref(''),error=ref('')
const expanded=ref(false),detail=ref<string|null>(null)
const confirm=ref<{task:QueueTask;action:'stop'|'retry'|'skip'}|null>(null)
const active=computed(()=>[...tasks.value].sort((a,b)=>a.seq-b.seq))
const blocking=computed(()=>active.value.find(hasBlockingFailure))
const clock=ref(Date.now())
const estimates=computed(()=>estimateQueue(active.value,history.value,clock.value))
async function refresh(){
  try{
    const [q,h]=await Promise.all([
      workQueueApi.list('active',200),
      workQueueApi.list('history',100)
    ])
    tasks.value=q.tasks;activeTotal.value=q.total
    history.value=h.tasks;historyTotal.value=h.total
    clock.value=Date.now()
    error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>void refresh())
usePolling(refresh,4000)
async function submit(){
  const target=confirm.value
  if(!target||busy.value)return
  const key=target.task.reference_job_id||target.task.fo_run_id||''
  busy.value=key
  try{
    if(target.task.kind==='fo_processing'){
      if(target.action!=='stop'||!target.task.fo_run_id)throw new Error('Неверное действие для ФО')
      await runApi.stop(target.task.fo_run_id)
    }else{
      const jobId=target.task.reference_job_id
      if(!jobId)throw new Error('Подготовка не найдена')
      if(target.action==='retry')await workQueueApi.retry(jobId,crypto.randomUUID())
      else if(target.action==='skip')await workQueueApi.skip(jobId,crypto.randomUUID())
      else await workQueueApi.stop(jobId)
    }
    notice.add(target.action==='retry'?'Подготовка возвращена в очередь':
      target.action==='skip'?'Обновление образцов явно пропущено':'Запрошена остановка','ok')
    confirm.value=null
    await refresh()
  }catch(e){error.value=errorText(e)}
  finally{busy.value=''}
}
function message(){
  if(!confirm.value)return ''
  return confirm.value.action==='retry'
    ?'Повторная подготовка сохранит исходное место в FIFO. Следующие ФО дождутся результата.'
    :confirm.value.action==='skip'
    ?'Новые образцы НЕ будут опубликованы. Следующие ФО продолжатся со старой версией библиотеки.'
    :'Текущее задание будет остановлено. Фотографии и уже полученные результаты не удаляются.'
}
</script>
<template>
<PageHeader eyebrow="ЕДИНАЯ FIFO" title="Очередь"
 subtitle="Обработка ФО и подготовка образцов в порядке поступления. Одно вычислительное задание одновременно.">
  <template #actions><UiButton small @click="refresh">Обновить</UiButton></template>
</PageHeader>
<div v-if="error" class="alert error" role="alert" style="margin-bottom:15px">{{error}}</div>
<div v-if="blocking" class="alert error" role="alert" style="margin-bottom:16px">
  <strong>Требуется исправить подготовку образцов.</strong>
  Следующие ФО не запускаются, пока вы не повторите подготовку или явно не пропустите обновление.
</div>
<div class="stack gap24">
  <section class="panel stack" aria-label="Общая очередь">
    <div class="row between wrap"><h2 style="margin:0">Ожидают и выполняются</h2>
      <span class="meta">{{activeTotal}} задач</span></div>
    <div v-if="!active.length" class="meta">Нет ожидающих заданий.</div>
    <QueueTaskRow v-for="(task,index) in active" :key="task.seq"
      :task="task" :position="index+1" :estimate="estimates.get(task.seq)" :busy="busy===task.reference_job_id||busy===task.fo_run_id"
      @action="(t,action)=>confirm={task:t,action}" @details="t=>detail=t.reference_job_id"/>
    <div v-if="activeTotal>active.length" class="meta">
      Показаны первые {{active.length}} из {{activeTotal}} задач.
    </div>
  </section>
  <QueueTaskDetail v-if="detail" :job-id="detail" @close="detail=null"/>
  <section class="panel stack" aria-label="История общей очереди">
    <div class="row between wrap"><h2 style="margin:0">История</h2>
      <UiButton small @click="expanded=!expanded">{{expanded?'Скрыть':'Показать'}} · {{historyTotal}}</UiButton></div>
    <template v-if="expanded">
      <QueueTaskRow v-for="task in history" :key="task.seq" :task="task"
        @details="t=>detail=t.reference_job_id"/>
      <span v-if="!history.length" class="meta">История пока пуста.</span>
    </template>
  </section>
</div>
<ConfirmDialog v-if="confirm" :busy="!!busy"
  :title="confirm.action==='retry'?'Повторить подготовку?':confirm.action==='skip'?'Пропустить обновление образцов?':'Остановить задачу?'"
  :message="message()" :danger="confirm.action!=='retry'"
  :confirm-label="confirm.action==='retry'?'Повторить':confirm.action==='skip'?'Пропустить обновление':'Остановить'"
  @cancel="confirm=null" @confirm="submit"/>
</template>
