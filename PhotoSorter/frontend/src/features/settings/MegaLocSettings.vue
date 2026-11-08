<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {runApi} from '../../api/runs'
import {useNoticeStore} from '../../stores/notice'
import {usePolling} from '../../composables/usePolling'
import {bytes,errorText} from '../../utils/format'
import type {ModelInfo} from '../../types/api'
import UiButton from '../../components/ui/UiButton.vue'

const notice=useNoticeStore()
const autoEnabled=ref(false),threshold=ref(.50),autoBusy=ref(false),autoReady=ref(false)
const model=ref<ModelInfo|null>(null),modelBusy=ref<string|null>(null),error=ref('')
const activeDownload=computed(()=>Object.values(model.value?.downloads||{}).some(
  value=>value.status==='downloading'||value.status==='verifying'))
async function refresh(){
  try{
    const [a,m]=await Promise.all([runApi.autoSettings(),runApi.models()])
    if(!autoBusy.value){autoEnabled.value=a.auto_process_new_batches;threshold.value=a.grouping_threshold}
    model.value=m;autoReady.value=true;error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>void refresh())
usePolling(refresh,5000)
async function saveAuto(){
  if(!autoReady.value||autoBusy.value)return
  autoBusy.value=true
  try{
    const next=await runApi.saveAutoSettings(autoEnabled.value,threshold.value)
    autoEnabled.value=next.auto_process_new_batches;threshold.value=next.grouping_threshold
    notice.add('Параметры автообработки сохранены','ok')
  }catch(e){error.value=errorText(e)}finally{autoBusy.value=false}
}
async function install(id:string,title:string){
  if(modelBusy.value||activeDownload.value)return
  modelBusy.value=id
  try{
    await runApi.installModel(id)
    notice.add('Установка '+title+' запущена','ok')
    await refresh()
  }catch(e){error.value=errorText(e)}
  finally{modelBusy.value=null}
}
function state(id:string){
  return model.value?.downloads?.[id]
}
function stateLabel(id:string,available:boolean){
  if(available)return 'Установлена'
  const value=state(id)
  if(value?.status==='downloading')return 'Устанавливается'
  if(value?.status==='verifying')return 'Проверяется'
  if(value?.status==='error')return 'Ошибка установки'
  return 'Не установлена'
}
</script>
<template>
<div class="stack gap24">
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <section class="panel stack" aria-label="Установка нейросетей">
    <div class="panel-header">
      <div>
        <h2>Нейросетевые модели</h2>
        <p class="meta" style="margin:5px 0">Установка на сервере · все модели работают на CPU</p>
      </div>
    </div>
    <p class="meta">Модели скачиваются и проверяются на сервере автоматически.
      Система устанавливает по одной модели, чтобы не перегружать VPS.
      Образцы и ФО при установке не удаляются.</p>
    <div v-if="!model" class="meta">Получение состояния моделей…</div>
    <div v-for="item in model?.models||[]" :key="item.id" class="model-installer-row">
      <div class="model-installer-main">
        <div class="row between wrap" style="gap:9px">
          <strong>{{item.title}}</strong>
          <span class="status" :class="item.available?'ok':state(item.id)?.status==='error'?'danger':''">
            {{stateLabel(item.id,item.available)}}
          </span>
        </div>
        <p class="meta" style="margin:5px 0 0">{{item.description}}</p>
        <p v-if="state(item.id)?.status==='downloading'||state(item.id)?.status==='verifying'"
          class="meta" role="status" style="margin:7px 0 0">
          {{state(item.id)?.message}}
          <span v-if="state(item.id)?.received_bytes">
            · загружено {{bytes(state(item.id)?.received_bytes)}}
          </span>
        </p>
        <p v-if="state(item.id)?.status==='error'" class="alert error" role="alert"
          style="margin:8px 0 0;white-space:pre-wrap;overflow-wrap:anywhere">
          {{state(item.id)?.message}}
        </p>
      </div>
      <UiButton v-if="!item.available" small :loading="modelBusy===item.id"
        :disabled="activeDownload||modelBusy!==null"
        @click="install(item.id,item.title)">
        {{state(item.id)?.status==='error'?'Повторить':'Установить'}}
      </UiButton>
      <span v-else class="meta model-installer-ready">Готова к работе</span>
    </div>
    <p class="meta">Во время загрузки отображается реально полученный объём данных,
      без выдуманного процента. После установки проверяются контрольные суммы.</p>
  </section>
  <section class="panel stack">
    <h2>Автоматическая обработка</h2>
    <label class="row" style="gap:10px">
      <input v-model="autoEnabled" type="checkbox" :disabled="!autoReady||autoBusy" @change="saveAuto"/>
      <strong>Автоматически обрабатывать загруженные ФО</strong>
    </label>
    <label class="field" style="max-width:380px">Порог группировки MegaLoc: {{threshold.toFixed(2)}}
      <input v-model.number="threshold" type="range" min=".50" max=".99" step=".01"
        :disabled="!autoReady||autoBusy" @change="saveAuto"/>
    </label>
    <p class="meta">Новые партии используют эти значения. Существующие задания не изменяются.</p>
  </section>
</div>
</template>
<style scoped>
.model-installer-row{display:flex;align-items:center;justify-content:space-between;
  gap:16px;padding:14px 0;border-top:1px solid var(--border-subtle)}
.model-installer-main{flex:1;min-width:0}
.model-installer-ready{white-space:nowrap}
@media(max-width:540px){.model-installer-row{align-items:flex-start;flex-wrap:wrap}}
</style>
