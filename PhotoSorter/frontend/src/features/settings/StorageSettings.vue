<script setup lang="ts">
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import {computed,onMounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {systemApi} from '../../api/system'
import {useNoticeStore} from '../../stores/notice'
import {usePolling} from '../../composables/usePolling'
import {bytes,date,errorText} from '../../utils/format'
import type {Batch,StorageUsage,StorageBreakdown,RetentionPreference} from '../../types/api'
import UiButton from '../../components/ui/UiButton.vue'
import UiSelect from '../../components/ui/UiSelect.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'

const notice=useNoticeStore()
const usageLoading=ref(true),retentionLoading=ref(true)
const usage=ref<StorageUsage|null>(null),batches=ref<Batch[]>([]),busy=ref(false),
  cleanConfirm=ref(false),error=ref(''),savingRetention=ref(false),retentionPrefs=ref<RetentionPreference|null>(null)
const breakdown=ref<StorageBreakdown|null>(null),scanning=ref(false),scanError=ref('')
const breakdownLabels:Record<string,string>={
  originals:'Оригиналы ФО',normalized:'Перекодированные ФО (.normalized)',
  results_files:'Готовые файлы результатов',results_zip:'ZIP готовых результатов',
  results_temporary:'Временные файлы результатов',reference_objects:'Хранилище объектов образцов',
  reference_gallery:'Галерея образцов',references_zip:'ZIP библиотеки образцов',
  reference_uploads:'Незавершённые загрузки образцов',reference_other:'Прочие файлы образцов',
  thumbnails:'Миниатюры ФО',reference_thumbnails:'Миниатюры образцов',reference_cache:'Кэш MegaLoc',other_cache:'Прочий кэш',
  runs:'Состояния запусков',logs:'Журналы',incoming:'Временные загрузки ФО',
  models:'Модели',other:'Другие файлы данных'
}
const breakdownRows=computed(()=>Object.entries(breakdown.value?.categories||{})
  .filter(([,stat])=>stat.files>0)
  .sort((a,b)=>b[1].allocated_bytes-a[1].allocated_bytes))
async function scanStorage(){
  if(scanning.value)return
  scanning.value=true;scanError.value=''
  try{breakdown.value=await systemApi.breakdown()}
  catch(e){scanError.value=errorText(e)}
  finally{scanning.value=false}
}
const due=computed(()=>batches.value.filter(b=>b.delete_state==='active'&&b.delete_after_at)
  .sort((a,b)=>(a.delete_after_at||'').localeCompare(b.delete_after_at||'')))
const labels:Record<string,string>={photos:'Оригиналы ФО',results:'Готовые результаты',
  references:'Образцы',reference_uploads:'Загрузки образцов',thumbnails:'Миниатюры ФО',reference_thumbnails:'Миниатюры образцов',reference_cache:'Кэш MegaLoc',
  models:'Модели',logs:'Журналы',runs:'Состояния запусков',incoming:'Временные загрузки',other:'Прочее'}
async function refresh(){
  try{
    const [u,b]=await Promise.all([systemApi.usage(),batchApi.list(200)])
    usage.value=u;batches.value=b.batches;error.value=''
  }catch(e){error.value=errorText(e)}finally{usageLoading.value=false}
}
onMounted(()=>{void refresh();void loadRetention()})
usePolling(refresh,20000)
async function loadRetention(){
  try{retentionPrefs.value=await systemApi.retention()}
  catch(e){error.value=errorText(e)}finally{retentionLoading.value=false}
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
      <p v-if="usage.registry" class="meta">Учёт: {{usage.registry.sampled_at?date(usage.registry.sampled_at):"ещё не готов"}} · {{usage.registry.partial?"сверка / ожидаются изменения":"сверено"}} · не найдено ожидаемых: {{usage.registry.missing_expected??0}} · расхождений: {{Object.values(usage.registry.issues||{}).reduce((a,b)=>a+b,0)}}</p>
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
    <LoadingSkeleton v-else-if="usageLoading" variant="lines" label="Считываем использование хранилища"/>
  </section>
  <section v-if="usage?.journals" class="panel stack">
    <h2>Бюджеты журналов</h2>
    <p class="meta">{{usage.journals.at?`Снимок: ${date(usage.journals.at)}`:"Снимок хостовых журналов ещё недоступен."}} Бюджеты допускают временное превышение на активный сегмент.</p>
    <div v-for="(row,name) in usage.journals.services" :key="name" class="row between wrap">
      <span>{{name}}</span><strong>{{row.bytes===null?"Нет данных":bytes(row.bytes)+(row.partial?" (частично)":"")}} / {{bytes(row.budget_bytes)}}</strong>
    </div>
  </section>
  <section class="panel stack">
    <div class="row between wrap">
      <div>
        <h2>Подробная диагностика диска</h2>
        <p class="meta">Показывает оригиналы, перекодирование, ZIP и hardlink по партиям.
          Только чтение: файлы не изменяются и ничего не удаляется.</p>
      </div>
      <UiButton :loading="scanning" :disabled="scanning" @click="scanStorage">
        {{breakdown?'Пересчитать':'Анализировать диск'}}
      </UiButton>
    </div>
    <p class="meta">Показатели берутся из автоматического реестра. Подробный отчёт запрашивается по кнопке, без повторного обхода диска.</p>
    <div v-if="scanError" class="alert error" role="alert">{{scanError}}</div>
    <template v-if="breakdown">
      <div v-if="breakdown.partial" class="alert warning" role="status">
        Анализ неполный: достигнут лимит или часть файлов была недоступна.
        Результаты ниже предварительные.
      </div>
      <div class="row wrap meta">
        <span>Проверено файлов: {{breakdown.files_scanned.toLocaleString('ru-RU')}}</span>
        <span>Время: {{breakdown.scan_seconds}} с</span>
        <span>Пропущено путей: {{breakdown.skipped_paths}}</span>
      </div>
      <div class="row between wrap">
        <strong>Учтено файловых блоков: {{bytes(breakdown.allocated_total_bytes)}}</strong>
        <span class="meta">Общие данные hardlink: {{bytes(breakdown.hardlink_reused_bytes)}}
          ({{breakdown.hardlink_paths}} ссылок)</span>
      </div>
      <p class="meta">
        «На диске» — оценка выделенных блоков, одинаковый inode учитывается один раз.
        «По файлам» — сумма размеров по путям без исключения hardlink.
        Это разные показатели, их не нужно складывать.
        Системные данные, PostgreSQL и Docker вне папок Sorter сюда не входят.
      </p>
      <div class="storage-breakdown-table">
        <div class="storage-breakdown-row storage-breakdown-head">
          <strong>Категория</strong><strong>На диске</strong><strong>По файлам</strong>
        </div>
        <div v-for="[key,stat] in breakdownRows" :key="key" class="storage-breakdown-row">
          <span>{{breakdownLabels[key]||key}} <small class="meta">({{stat.files}})</small></span>
          <strong>{{bytes(stat.allocated_bytes)}}</strong>
          <span class="meta">{{bytes(stat.logical_bytes)}}</span>
        </div>
      </div>
      <template v-if="breakdown.reference_history">
        <h3>Образцы, сохранённые только в истории</h3>
        <div class="row wrap meta">
          <span>Объекты: {{breakdown.reference_history.objects}} / {{bytes(breakdown.reference_history.object_bytes)}}</span>
          <span>Эмбеддинги: {{breakdown.reference_history.embeddings}} / {{bytes(breakdown.reference_history.embedding_bytes)}}</span>
          <span v-if="breakdown.reference_history.missing">Недоступно файлов: {{breakdown.reference_history.missing}}</span>
          <span v-if="breakdown.reference_history.partial">Ограниченная выборка</span>
        </div>
        <p class="meta">Это часть общего объёма образцов и кэша, а не дополнительные байты. Используемые версии не удаляются по возрасту.</p>
      </template>
      <p v-else-if="breakdown.reference_history===null" class="meta">Данные истории образцов временно недоступны.</p>
      <h3>Партии ФО — больше всего места</h3>
      <p v-if="!breakdown.batch_metadata_available" class="meta">
        Метаданные партий временно недоступны, ниже могут отсутствовать подписи.
      </p>
      <p v-if="!breakdown.batches.length" class="meta">Партии для этого анализа не найдены.</p>
      <div v-for="batch in breakdown.batches.slice(0,20)" :key="batch.batch_id"
        class="storage-batch-row">
        <div class="row between wrap">
          <RouterLink :to="'/fo/'+batch.batch_id"><strong>{{batch.display_name}}</strong></RouterLink>
          <strong>{{bytes(batch.allocated_bytes)}} на диске</strong>
        </div>
        <div class="row wrap meta">
          <span>Оригиналы: {{bytes(batch.originals.allocated_bytes)}}</span>
          <span>Перекодировано: {{bytes(batch.normalized.allocated_bytes)}}</span>
          <span>Файлы результатов: {{bytes(batch.results_files.allocated_bytes)}}</span>
          <span>ZIP: {{bytes(batch.results_zip.allocated_bytes)}}</span>
          <span>Hardlink: {{bytes(batch.hardlink_reused_bytes)}} без повторного места</span>
        </div>
      </div>
      <p v-if="breakdown.total_batches>20" class="meta">
        Показаны первые 20 из {{breakdown.total_batches}} партий по занятому месту.
      </p>
    </template>
  </section>
  <section class="panel stack">
    <div class="row between wrap">
      <div><h2>Автоматическое удаление</h2><p class="meta">После обработки удаляются исходные ФО, результаты и ZIP.</p></div>
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
    <p class="meta">Отсчёт начинается после завершения ZIP. Новый срок действует для следующих обработок; существующие сроки сохраняются. При выключении автоудаление приостанавливается для всех партий. После повторного включения просроченные партии получат новый срок.</p>
    <h3>Назначенные сроки удаления</h3>
    <div v-for="batch in due" :key="batch.batch_id" class="row between wrap"
      style="border-bottom:1px solid var(--border-subtle);padding:10px 0">
      <div><RouterLink :to="'/fo/'+batch.batch_id"><strong>{{batch.display_name}}</strong></RouterLink>
        <div class="meta">Удаление: {{date(batch.delete_after_at)}}</div></div>
      <UiButton small :loading="busy" @click="extend(batch.batch_id)">Продлить</UiButton>
    </div>
    <p v-if="!usageLoading&&!due.length&&usage" class="meta">Пока нет партий с назначенным сроком удаления.</p>
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

<style scoped>
.storage-breakdown-table{display:grid;gap:0}
.storage-breakdown-row{display:grid;grid-template-columns:minmax(0,1fr) 110px 110px;
  align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-subtle)}
.storage-breakdown-row>:nth-child(n+2){text-align:right}
.storage-breakdown-head{font-size:12px;color:var(--muted)}
.storage-batch-row{padding:13px 0;border-bottom:1px solid var(--border-subtle);display:grid;gap:6px}
@media(max-width:550px){
  .storage-breakdown-row{grid-template-columns:minmax(0,1fr) 84px 84px;gap:6px;font-size:12px}
}
</style>
