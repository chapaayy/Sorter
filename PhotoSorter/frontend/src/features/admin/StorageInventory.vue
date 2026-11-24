<script setup lang="ts">
import {computed,ref} from 'vue'
import UiButton from '../../components/ui/UiButton.vue'
import {systemApi} from '../../api/system'
import {bytes,errorText} from '../../utils/format'
import type {StorageInventoryPage,StorageInventorySummary} from '../../types/api'

const summary=ref<StorageInventorySummary|null>(null)
const page=ref<StorageInventoryPage|null>(null)
const scanning=ref(false),loading=ref(false),error=ref('')
const category=ref(''),search=ref(''),appliedSearch=ref('')
const categoryNames:Record<string,string>={
  originals:'Оригиналы ФО',normalized:'Перекодированные ФО',
  results_files:'Результаты',results_zip:'ZIP результатов',
  results_temporary:'Временные результаты',reference_objects:'Объекты образцов',
  reference_gallery:'Галерея образцов',references_zip:'ZIP образцов',
  reference_uploads:'Загрузка образцов',reference_other:'Прочие образцы',
  thumbnails:'Миниатюры ФО',reference_thumbnails:'Миниатюры образцов',reference_cache:'Признаки MegaLoc',
  other_cache:'Кэши',runs:'Данные обработок',logs:'Журналы',
  incoming:'Незавершённые загрузки',models:'Модели',other:'Прочее'
}
const purposeNames:Record<string,string>={
  permanent:'Постоянный',temporary:'Временный',cache:'Кэш',
  system:'Системный',service:'Служебный',archive:'Архив',unknown:'Не определён'
}
const reportUrl=computed(()=>summary.value
  ? '/api/storage/inventory/report.csv?snapshot_id='+encodeURIComponent(summary.value.snapshot_id)
  : '')
const reportFilename=computed(()=>{
  const value=summary.value
  if(!value)return 'map-file-inventory.csv'
  const date=value.captured_at.slice(0,10).replace(/-/g,'')
  const time=value.captured_at.slice(11,19).replace(/:/g,'')
  return 'map-file-inventory-'+date+'_'+time+(value.partial?'-partial':'')+'.csv'
})
const availableCategories=computed(()=>Object.entries(summary.value?.categories||{})
  .filter(([,value])=>value.files>0)
  .sort((a,b)=>b[1].allocated_bytes-a[1].allocated_bytes))
async function loadPage(offset=0){
  if(!summary.value||loading.value)return
  loading.value=true;error.value=''
  try{page.value=await systemApi.inventoryFiles(summary.value.snapshot_id,offset,category.value,appliedSearch.value)}
  catch(e){error.value=errorText(e)}
  finally{loading.value=false}
}
async function scan(){
  if(scanning.value)return
  scanning.value=true;error.value=''
  try{
    const next=await systemApi.scanInventory()
    summary.value=next
    page.value=null
    await loadPage(0)
  }catch(e){error.value=errorText(e)}
  finally{scanning.value=false}
}
function applyFilters(){
  appliedSearch.value=search.value.trim()
  void loadPage(0)
}
</script>

<template>
  <section class="panel stack">
    <div class="row between wrap">
      <div class="stack" style="gap:4px">
        <h2>Учёт файлов MAP</h2>
        <p class="meta">Проверка файлов на диске: пути, размеры, категории и связь с ФО.
          Только чтение — без удаления, лимитов и изменений в обработке.</p>
      </div>
      <div class="row wrap">
        <a v-if="summary&&!scanning" class="btn secondary" :href="reportUrl" :download="reportFilename"
          title="Скачать все файлы из последней проверки, без ограничения в 100 строк">
          Скачать полный отчёт CSV
        </a>
        <UiButton :loading="scanning" :disabled="scanning" @click="scan">
          {{summary?'Повторить проверку':'Проверить файлы'}}
        </UiButton>
      </div>
    </div>
    <div v-if="error" class="alert error" role="alert">{{error}}</div>
    <p v-if="scanning" class="meta" role="status">Проверяем файлы на диске…</p>
    <template v-if="summary">
      <div class="row wrap meta">
        <span>Файлов: {{summary.files_scanned.toLocaleString('ru-RU')}}</span>
        <span>На диске: {{bytes(summary.allocated_bytes)}}</span>
        <span>Проверка: {{summary.scan_seconds}} с</span>
      </div>
      <div v-if="summary.partial" class="alert warning" role="status">
        Проверка неполная (лимит времени/файлов, недоступные пути или символьные ссылки).
        Пропущено: {{summary.skipped_paths}}. Нельзя считать этот снимок полным учётом.
      </div>
      <p class="meta">CSV содержит все {{summary.files_scanned.toLocaleString('ru-RU')}} файлов последней проверки
        независимо от фильтров и страниц. Скачивание не создаёт архивов на сервере.</p>
      <p class="meta">Показан снимок на момент проверки, а не история всех записей.
        Файлы, созданные или удалённые после проверки, появятся после следующего сканирования.
        Одинаковые hardlink учитываются на диске один раз.</p>
      <div class="storage-inventory-filter row wrap">
        <label class="field">
          Категория
          <select v-model="category" aria-label="Категория файлов" @change="applyFilters">
            <option value="">Все категории</option>
            <option v-for="[key,stat] in availableCategories" :key="key" :value="key">
              {{categoryNames[key]||key}} ({{stat.files}})
            </option>
          </select>
        </label>
        <label class="field">
          Поиск по пути или ФО
          <input v-model="search" type="search" placeholder="Например: SAM 0004 или .tmp"
            aria-label="Поиск файлов" @keyup.enter="applyFilters"/>
        </label>
        <UiButton :disabled="loading" @click="applyFilters">Найти</UiButton>
      </div>
      <div class="storage-inventory-list" aria-live="polite">
        <div v-for="item in page?.files||[]" :key="item.path" class="storage-inventory-item">
          <div class="row between wrap">
            <strong>{{categoryNames[item.category]||item.category}}</strong>
            <strong>{{bytes(item.allocated_bytes)}} на диске</strong>
          </div>
          <code class="inventory-path">{{item.path}}</code>
          <div class="row wrap meta">
            <span>{{purposeNames[item.purpose]||item.purpose}}</span>
            <span>Размер: {{bytes(item.logical_bytes)}}</span>
            <span v-if="item.hardlink">Hardlink: без повторного места</span>
            <span v-else-if="item.links>1">Физических ссылок: {{item.links}}</span>
            <span v-if="item.owner_name">ФО: {{item.owner_name}}</span>
            <span v-else-if="item.owner_id">Связь: {{item.owner_kind}} / {{item.owner_id}}</span>
          </div>
        </div>
        <p v-if="page&&!page.files.length" class="meta">Файлы по этому фильтру не найдены.</p>
      </div>
      <div v-if="page" class="row between wrap">
        <span class="meta">Показаны {{page.total? page.offset+1:0}}–{{Math.min(page.offset+page.files.length,page.total)}}
          из {{page.total.toLocaleString('ru-RU')}}</span>
        <div class="row">
          <UiButton small :disabled="loading||page.offset===0"
            @click="loadPage(Math.max(0,(page?.offset||0)-100))">Назад</UiButton>
          <UiButton small :disabled="loading||page.offset+page.files.length>=page.total"
            @click="loadPage((page?.offset||0)+100)">Дальше</UiButton>
        </div>
      </div>
      <details>
        <summary>Что пока не учитывается по отдельным файлам</summary>
        <p class="meta">Приложение видит только подключённые каталоги данных и моделей.
          Системные Docker-тома и временные файлы вне этих каталогов требуют отдельного мониторинга.</p>
        <ul><li v-for="item in summary.not_scanned" :key="item">{{item}}</li></ul>
      </details>
    </template>
  </section>
</template>

<style scoped>
.storage-inventory-filter{align-items:end;gap:12px}
.storage-inventory-filter .field{min-width:180px;flex:1;max-width:360px}
.storage-inventory-filter .field input,.storage-inventory-filter .field select{width:100%}
.storage-inventory-list{display:grid;gap:0}
.storage-inventory-item{display:grid;gap:7px;padding:14px 0;border-bottom:1px solid var(--border-subtle);min-width:0}
.inventory-path{white-space:normal;overflow-wrap:anywhere;font-size:12px;color:var(--text)}
details{font-size:13px}
@media(max-width:550px){.storage-inventory-filter .field{max-width:none;width:100%}}
</style>
