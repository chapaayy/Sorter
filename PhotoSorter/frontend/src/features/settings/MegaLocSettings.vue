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
const model=ref<ModelInfo|null>(null),modelBusy=ref(false),error=ref('')
async function refresh(){
  try{
    const [a,m]=await Promise.all([runApi.autoSettings(),runApi.models()])
    if(!autoBusy.value){autoEnabled.value=a.auto_process_new_batches;threshold.value=a.grouping_threshold}
    model.value=m;autoReady.value=true;error.value=''
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

</div>
</template>
