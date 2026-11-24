<script setup lang="ts">
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import {computed,onMounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {systemApi} from '../../api/system'
import {useNoticeStore} from '../../stores/notice'
import {date,errorText} from '../../utils/format'
import type {Batch,RetentionPreference} from '../../types/api'
import UiButton from '../../components/ui/UiButton.vue'
import UiSelect from '../../components/ui/UiSelect.vue'
const notice=useNoticeStore()
const loading=ref(true),retentionLoading=ref(true),busy=ref(false),savingRetention=ref(false),error=ref('')
const batches=ref<Batch[]>([]),retentionPrefs=ref<RetentionPreference|null>(null)
const due=computed(()=>batches.value.filter(b=>b.delete_state==='active'&&b.delete_after_at)
  .sort((a,b)=>(a.delete_after_at||'').localeCompare(b.delete_after_at||'')))
async function refresh(){
  loading.value=true
  try{batches.value=(await batchApi.list(200)).batches}
  catch(e){error.value=errorText(e)}finally{loading.value=false}
}
async function loadRetention(){
  try{retentionPrefs.value=await systemApi.retention()}
  catch(e){error.value=errorText(e)}finally{retentionLoading.value=false}
}
onMounted(()=>{void refresh();void loadRetention()})
async function saveRetention(){
  if(!retentionPrefs.value||savingRetention.value)return
  savingRetention.value=true
  try{retentionPrefs.value=await systemApi.saveRetention(retentionPrefs.value)
    notice.add('Срок хранения для новых обработок сохранён','ok');error.value=''
  }catch(e){error.value=errorText(e)}finally{savingRetention.value=false}
}
async function extend(id:string){
  busy.value=true
  try{await batchApi.extend(id);notice.add('Срок хранения продлён','ok');await refresh()}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="stack">
  <p v-if="error" role="alert" class="alert error">{{error}}</p>
  <section class="panel stack">
    <div class="row between wrap">
      <div><h2>Автоматическое удаление</h2><p class="meta">Действующая политика хранения фотоотчётов.</p></div>
      <UiButton :disabled="!retentionPrefs" :loading="savingRetention" @click="saveRetention">Сохранить</UiButton>
    </div>
    <LoadingSkeleton v-if="retentionLoading" variant="lines" :count="2" label="Загружаем срок хранения"/>
    <label v-if="retentionPrefs" class="row" style="gap:10px">
      <input v-model="retentionPrefs.enabled" type="checkbox"/>
      <strong>Удалять старые фотоотчёты автоматически</strong>
    </label>
    <div v-if="retentionPrefs?.enabled" class="row wrap" style="gap:12px;align-items:end">
      <label class="field" style="max-width:180px;flex:1">Удалять через
        <input v-model.number="retentionPrefs.value" type="number" min="1"
          :max="retentionPrefs.unit==='months'?120:525600" step="1"/>
      </label>
      <div style="min-width:165px;flex:1;max-width:220px">
        <UiSelect label="Единицы срока хранения" :model-value="retentionPrefs.unit"
          :options="[{value:'minutes',label:'Минут'},{value:'hours',label:'Часов'},
                     {value:'days',label:'Дней'},{value:'months',label:'Месяцев'}]"
          @update:model-value="retentionPrefs.unit=$event as RetentionPreference['unit']"/>
      </div>
    </div>
    <p class="meta">Отсчёт начинается по действующей политике после подтверждения скачивания. Новый срок действует для следующих обработок; существующие сроки сохраняются. При выключении автоудаление приостанавливается для всех партий. После повторного включения просроченные партии получат новый срок.</p>
    <h3>Назначенные сроки удаления</h3>
    <div v-for="batch in due" :key="batch.batch_id" class="row between wrap"
      style="border-bottom:1px solid var(--border-subtle);padding:10px 0">
      <div><RouterLink :to="'/fo/'+batch.batch_id"><strong>{{batch.display_name}}</strong></RouterLink>
        <div class="meta">Удаление: {{date(batch.delete_after_at)}}</div></div>
      <UiButton small :loading="busy" @click="extend(batch.batch_id)">Продлить</UiButton>
    </div>
    <p v-if="!loading&&!due.length" class="meta">Пока нет партий с назначенным сроком удаления.</p>
  </section>

  <p class="meta">Список сроков содержит до 200 последних фотоотчётов.</p>
</div>
</template>
