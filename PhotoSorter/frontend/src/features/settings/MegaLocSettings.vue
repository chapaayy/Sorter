<script setup lang="ts">
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import {onMounted,ref} from 'vue'
import {runApi} from '../../api/runs'
import {useNoticeStore} from '../../stores/notice'
import {usePolling} from '../../composables/usePolling'
import {errorText} from '../../utils/format'
import type {ModelInfo} from '../../types/api'
import UiButton from '../../components/ui/UiButton.vue'

const notice=useNoticeStore()
const autoEnabled=ref(false),threshold=ref(.50),minScore=ref(0),autoBusy=ref(false),autoReady=ref(false)
const initialLoading=ref(true)
const model=ref<ModelInfo|null>(null),modelBusy=ref(false),error=ref('')
async function refresh(){
  try{
    const [a,m]=await Promise.all([runApi.autoSettings(),runApi.models()])
    if(!autoBusy.value){autoEnabled.value=a.auto_process_new_batches;threshold.value=a.grouping_threshold;minScore.value=a.min_match_score}
    model.value=m;autoReady.value=true;error.value=''
  }catch(e){error.value=errorText(e)}finally{initialLoading.value=false}
}
onMounted(()=>void refresh())
usePolling(refresh,15000)
async function saveAuto(){
  if(!autoReady.value||autoBusy.value)return
  autoBusy.value=true
  try{
    const next=await runApi.saveAutoSettings(autoEnabled.value,threshold.value,minScore.value)
    autoEnabled.value=next.auto_process_new_batches;threshold.value=next.grouping_threshold;minScore.value=next.min_match_score
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
      <span v-if="model" class="status" :class="model?.models[0]?.available?'ok':'danger'">
        {{model?.models[0]?.available?'Модель установлена':'Модель не найдена'}}
      </span>
    </div>
    <LoadingSkeleton v-if="initialLoading" variant="lines" :count="2" label="Проверяем MegaLoc"/>
    <div v-else-if="model" class="row between wrap"><div><strong>Устройство: CPU</strong><div class="meta">Единственная модель сортировки</div></div>
      <UiButton v-if="model&&!model.models[0]?.available" :loading="modelBusy" @click="install">Установить MegaLoc</UiButton>
    </div>
  </section>
  <section class="panel stack">
    <h2>Автоматическая обработка</h2>
    <LoadingSkeleton v-if="initialLoading" variant="lines" :count="2" label="Загружаем параметры MegaLoc"/>
    <template v-else-if="autoReady">
    <label class="row" style="gap:10px">
      <input v-model="autoEnabled" type="checkbox" :disabled="!autoReady||autoBusy" @change="saveAuto"/>
      <strong>Автоматически обрабатывать загруженные ФО</strong>
    </label>
    <label class="field" style="max-width:380px">Порог группировки: {{threshold.toFixed(2)}}
      <input v-model.number="threshold" type="range" min=".50" max=".99" step=".01"
        :disabled="!autoReady||autoBusy" @change="saveAuto"/>
    </label>
    <p class="meta">Порог группировки влияет только на связь ФО между собой. Для автоматических новых партий он берётся из этих настроек.</p>
    </template>
  </section>
  <section class="panel stack">
    <h2>Минимальное сходство с образцами</h2>
    <LoadingSkeleton v-if="initialLoading" variant="lines" :count="2" label="Загружаем настройки качества"/>
    <template v-else-if="autoReady">
      <div class="row between wrap" style="gap:16px">
        <div>
          <strong>{{minScore===0?'Фильтр отключён':'Порог: '+minScore.toFixed(3)}}</strong>
          <p class="meta" style="margin-top:6px">От 0.000 до 1.000 · 0.000 — не отсеивать</p>
        </div>
        <label class="field" style="width:130px">Значение
          <input v-model.number="minScore" type="number" min="0" max="1" step="0.001"
            :disabled="autoBusy" @change="saveAuto" aria-label="Минимальное сходство с образцами"/>
        </label>
      </div>
      <input v-model.number="minScore" type="range" min="0" max="1" step=".001"
        :disabled="autoBusy" @change="saveAuto" aria-label="Настроить порог сходства с образцами"/>
      <p class="meta">Например, при 0.200 фотография с оценкой 0.097 попадёт в «Неопределено»,
        а с оценкой 0.234 — останется. Проверяется каждая ФО отдельно, даже внутри одной группы.</p>
      <p class="meta">Порог действует на новые ручные и автоматические запуски. Уже обрабатываемые и готовые результаты не меняются.
        Группировка и расчёт MegaLoc остаются прежними.</p>
    </template>
  </section>

</div>
</template>
