<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {runApi} from '../../api/runs'
import type {WorkloadSettings} from '../../types/api'
import {errorText} from '../../utils/format'
import {useNoticeStore} from '../../stores/notice'
import UiButton from '../../components/ui/UiButton.vue'
const data=ref<WorkloadSettings|null>(null),busy=ref(false),error=ref('')
const notice=useNoticeStore()
const model=computed({get:()=>data.value?.model_cpus??1,set:(value:number)=>{
  if(data.value)data.value.model_cpus=Math.min(data.value.max_model_cpus,Math.max(1,value))
}})
const system=computed({get:()=>data.value?data.value.total_cpus-model.value:0,set:(value:number)=>{
  if(data.value)model.value=data.value.total_cpus-value
}})
const percent=computed(()=>data.value?100*model.value/data.value.total_cpus:0)
async function load(){try{data.value=await runApi.workloadSettings();error.value=''}catch(e){error.value=errorText(e)}}
onMounted(()=>void load())
async function save(){
 if(!data.value||busy.value)return
 busy.value=true
 try{
  data.value=await runApi.saveCpuBudget(model.value)
  notice.add('Распределение CPU сохранено для следующих задач','ok');error.value=''
 }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="stack gap24">
 <div v-if="error" class="alert error" role="alert">{{error}}</div>
 <section v-if="data" class="panel stack gap24" aria-label="Распределение CPU">
  <div class="row between wrap">
   <div><h2>Производительность</h2><p class="meta">{{data.total_cpus}} доступных vCPU · единая очередь MegaLoc</p></div>
   <UiButton small :loading="busy" @click="save">Сохранить</UiButton>
  </div>
  <div class="cpu-budget-track" role="img" :aria-label="'Модель '+model+' CPU, системный резерв '+system+' CPU'">
   <span class="cpu-budget-model" :style="{width:percent+'%'}"/><span class="cpu-budget-system" :style="{width:(100-percent)+'%'}"/>
  </div>
  <div class="grid2">
   <label class="field"><strong>Модель · {{model}} CPU</strong>
    <span class="meta">Группировка и сопоставление ФО или подготовка Образцов — по очереди</span>
    <input v-model.number="model" type="range" min="1" :max="data.max_model_cpus" step="1" aria-label="CPU модели"/>
   </label>
   <label class="field"><strong>Система · {{system}} CPU</strong>
    <span class="meta">Резерв свободных от модели ядер для сайта, базы, миниатюр и очистки</span>
    <input v-model.number="system" type="range" :min="data.total_cpus-data.max_model_cpus" :max="data.total_cpus-1" step="1" aria-label="Резерв CPU системы"/>
   </label>
  </div>
  <p class="meta">Модель ограничивается количеством потоков и набором допустимых CPU при начале следующего задания. Система не запирается в резерве: при свободной модели другие службы могут использовать все доступные ядра.</p>
 </section>
 <section class="panel stack">
  <h2>Фоновые службы</h2>
  <p class="meta">Миниатюры и очистка выполняются в отдельных контейнерах с низким CPU-приоритетом и без жёстких квот. Linux распределяет свободное процессорное время автоматически.</p>
  <div class="row between wrap"><strong>Создание миниатюр</strong><span class="meta">Низкий приоритет</span></div>
  <div class="row between wrap"><strong>Очистка данных</strong><span class="meta">Минимальный приоритет</span></div>
  <div class="row between wrap"><strong>ZIP-архив</strong><span class="meta">Без изменений · завершающий этап задачи</span></div>
 </section>
</div>
</template>
<style scoped>
.cpu-budget-track{display:flex;width:100%;height:14px;overflow:hidden;border-radius:999px;gap:2px;background:var(--panel-alt)}
.cpu-budget-model{background:#4b90e8;transition:width .15s}.cpu-budget-system{background:#9299a4;transition:width .15s}
.field{gap:10px}.field input[type=range]{width:100%;accent-color:#4b90e8}
@media(max-width:700px){.grid2{grid-template-columns:1fr}}
</style>
