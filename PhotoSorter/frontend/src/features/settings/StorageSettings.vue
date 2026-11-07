<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {systemApi} from '../../api/system'
import {useNoticeStore} from '../../stores/notice'
import {usePolling} from '../../composables/usePolling'
import {bytes,date,errorText} from '../../utils/format'
import type {Batch,StorageUsage,RetentionPreference} from '../../types/api'
import UiButton from '../../components/ui/UiButton.vue'
import UiSelect from '../../components/ui/UiSelect.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'

const notice=useNoticeStore()
const usage=ref<StorageUsage|null>(null),batches=ref<Batch[]>([]),busy=ref(false),
  cleanConfirm=ref(false),error=ref(''),savingRetention=ref(false),retentionPrefs=ref<RetentionPreference|null>(null)
const due=computed(()=>batches.value.filter(b=>b.delete_state==='active'&&b.delete_after_at)
  .sort((a,b)=>(a.delete_after_at||'').localeCompare(b.delete_after_at||'')))
const labels:Record<string,string>={photos:'Оригиналы ФО',results:'Готовые результаты',
  references:'Образцы',thumbnails:'Миниатюры',reference_cache:'Кэш MegaLoc',
  models:'Модели',logs:'Журналы',runs:'Состояния запусков',incoming:'Временные загрузки',other:'Прочее'}
async function refresh(){
  try{
    const [u,b]=await Promise.all([systemApi.usage(),batchApi.list(200)])
    usage.value=u;batches.value=b.batches;error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>{void refresh();void loadRetention()})
usePolling(refresh,20000)
async function loadRetention(){
  try{retentionPrefs.value=await systemApi.retention()}
  catch(e){error.value=errorText(e)}
}
async function saveRetention(){
  if(!retentionPrefs.value||savingRetention.value)return
  savingRetention.value=true
  try{
    retentionPrefs.value=await systemApi.saveRetention(retentionPrefs.value)
    notice.add('Срок хранения для новых обработок сохранён','ok');error.value=''
  }catch(e){error.value=errorText(e)}
  finally{savingRetention.value=false}
}
async function extend(id:string){
  busy.value=true
  try{
    await batchApi.extend(id);notice.add('Срок хранения продлён','ok')
    await refresh()
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function cleanup(){
  busy.value=true
  try{
    const result=await systemApi.cleanup()
    cleanConfirm.value=false
    notice.add('Удалено неиспользуемых миниатюр: '+result.removed,'ok')
    await refresh()
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="stack gap24">
  <div v-if="error" class="alert error">{{error}}</div>
  <section class="panel stack">
    <div class="panel-header"><h2>Дисковое пространство</h2>
      <span v-if="usage?.disk.warning" class="status" :class="usage.disk.warning==='critical'?'danger':''">
        {{usage.disk.warning==='critical'?'Мало места':'Место заканчивается'}}
      </span>
    </div>
    <template v-if="usage">
      <div class="row between wrap">
        <strong style="font-size:21px">{{bytes(usage.disk.used_bytes)}} / {{bytes(usage.disk.total_bytes)}}</strong>
        <span class="meta">Свободно: {{bytes(usage.disk.available_bytes)}}</span>
      </div>
      <div class="progress-track"><span class="progress-fill"
        :style="{width:Math.round(usage.disk.used_fraction*100)+'%'}"/></div>
      <div class="grid2">
        <div v-for="(value,key) in usage.categories_bytes" :key="key"
          class="row between" style="padding:9px 0;border-bottom:1px solid var(--border-subtle)">
          <span class="meta">{{labels[key]||key}}</span><strong>{{bytes(value)}}</strong>
        </div>
        <div class="row between"><span class="meta">PostgreSQL (оценка)</span>
          <strong>{{bytes(usage.database_estimated_bytes)}}</strong></div>
      </div>
    </template>
    <p v-else class="meta">Считываем использование хранилища…</p>
  </section>
  <section class="panel stack">
    <div class="row between wrap">
      <div><h2>Автоматическое удаление</h2><p class="meta">После обработки удаляются исходные ФО, результаты и ZIP.</p></div>
      <UiButton :disabled="!retentionPrefs" :loading="savingRetention" @click="saveRetention">Сохранить</UiButton>
    </div>
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
    <p class="meta">Отсчёт начинается после завершения ZIP. Новый срок действует для следующих обработок; существующие сроки сохраняются. При выключении автоудаление приостанавливается для всех партий. После повторного включения просроченные партии получат новый срок.</p>
    <h3>Назначенные сроки удаления</h3>
    <div v-for="batch in due" :key="batch.batch_id" class="row between wrap"
      style="border-bottom:1px solid var(--border-subtle);padding:10px 0">
      <div><RouterLink :to="'/fo/'+batch.batch_id"><strong>{{batch.display_name}}</strong></RouterLink>
        <div class="meta">Удаление: {{date(batch.delete_after_at)}}</div></div>
      <UiButton small :loading="busy" @click="extend(batch.batch_id)">Продлить</UiButton>
    </div>
    <p v-if="!due.length" class="meta">Пока нет партий с назначенным сроком удаления.</p>
  </section>
  <section class="panel stack">
    <div class="row between wrap">
      <div><h2>Кэш миниатюр</h2>
        <p class="meta">Оригиналы и готовые результаты не затрагиваются.</p>
      </div>
      <UiButton :loading="busy" @click="cleanConfirm=true">Очистить неиспользуемое</UiButton>
    </div>
  </section>
  <ConfirmDialog v-if="cleanConfirm" title="Очистить неиспользуемые миниатюры?"
    message="Удалятся только не принадлежащие фотографиям миниатюры."
    confirm-label="Очистить" :busy="busy" @confirm="cleanup" @cancel="cleanConfirm=false"/>
</div>
</template>
