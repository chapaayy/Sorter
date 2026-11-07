<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {runApi} from '../../api/runs'
import {useNoticeStore} from '../../stores/notice'
import {usePolling} from '../../composables/usePolling'
import {errorText} from '../../utils/format'
import type {ModelInfo} from '../../types/api'
import UiButton from '../../components/ui/UiButton.vue'

const notice=useNoticeStore()
const autoEnabled=ref(false),threshold=ref(.50),autoBusy=ref(false),autoReady=ref(false)
const threads=ref(7),maxThreads=ref(8),cpuBusy=ref(false),cpuReady=ref(false)
const model=ref<ModelInfo|null>(null),modelBusy=ref(false),error=ref('')
async function refresh(){
  try{
    const [a,c,m]=await Promise.all([runApi.autoSettings(),runApi.cpuSettings(),runApi.models()])
    if(!autoBusy.value){autoEnabled.value=a.auto_process_new_batches;threshold.value=a.grouping_threshold}
    if(!cpuBusy.value){threads.value=c.threads;maxThreads.value=c.max_threads}
    model.value=m;autoReady.value=true;cpuReady.value=true;error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>void refresh())
usePolling(refresh,15000)
async function saveAuto(){
  if(!autoReady.value||autoBusy.value)return
  autoBusy.value=true
  try{
    const next=await runApi.saveAutoSettings(autoEnabled.value,threshold.value)
    autoEnabled.value=next.auto_process_new_batches;threshold.value=next.grouping_threshold
    notice.add('Параметры автообработки сохранены','ok')
  }catch(e){error.value=errorText(e)}finally{autoBusy.value=false}
}
async function saveCpu(){
  if(!cpuReady.value||cpuBusy.value)return
  cpuBusy.value=true
  try{
    const next=await runApi.saveCpuThreads(threads.value)
    threads.value=next.threads
    notice.add('Потоки MegaLoc изменятся со следующего задания','ok')
  }catch(e){error.value=errorText(e)}finally{cpuBusy.value=false}
}
async function install(){
  if(modelBusy.value)return
  modelBusy.value=true
  try{
    await runApi.downloadModel()
    notice.add('Загрузка MegaLoc запущена','ok')
    await refresh()
  }catch(e){error.value=errorText(e)}finally{modelBusy.value=false}
}
</script>
<template>
<div class="stack gap24">
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <section class="panel stack">
    <div class="panel-header"><h2>MegaLoc</h2>
      <span class="status" :class="model?.models[0]?.available?'ok':'danger'">
        {{model?.models[0]?.available?'Модель установлена':'Модель не найдена'}}
      </span>
    </div>
    <div class="row between wrap"><div><strong>Устройство: CPU</strong><div class="meta">Единственная модель сортировки</div></div>
      <UiButton v-if="model&&!model.models[0]?.available" :loading="modelBusy" @click="install">Установить MegaLoc</UiButton>
    </div>
  </section>
  <section class="panel stack">
    <h2>Автоматическая обработка</h2>
    <label class="row" style="gap:10px">
      <input v-model="autoEnabled" type="checkbox" :disabled="!autoReady||autoBusy" @change="saveAuto"/>
      <strong>Автоматически обрабатывать загруженные ФО</strong>
    </label>
    <label class="field" style="max-width:380px">Порог группировки: {{threshold.toFixed(2)}}
      <input v-model.number="threshold" type="range" min=".50" max=".99" step=".01"
        :disabled="!autoReady||autoBusy" @change="saveAuto"/>
    </label>
    <p class="meta">Новые партии используют эти значения. Существующие задания не изменяются.</p>
  </section>
  <section class="panel stack">
    <h2>Производительность CPU</h2>
    <div class="row between wrap">
      <div>
        <strong>Потоки MegaLoc: {{threads}}</strong>
        <p class="meta" style="margin:4px 0 0">Число вычислительных потоков при загрузке следующей задачи</p>
      </div>
      <UiButton small :disabled="!cpuReady||cpuBusy" :loading="cpuBusy" @click="saveCpu">Применить</UiButton>
    </div>
    <input v-model.number="threads" type="range" min="1" :max="maxThreads" step="1"
      :disabled="!cpuReady||cpuBusy" aria-label="Число потоков CPU для MegaLoc"/>
    <div class="meta">Лимит Docker не изменяется. Настройка применяется перед следующей ФО или подготовкой образцов. Максимум ограничен доступными CPU Worker.</div>
  </section>
</div>
</template>
