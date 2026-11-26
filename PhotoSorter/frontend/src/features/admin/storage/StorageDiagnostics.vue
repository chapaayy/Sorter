<script setup lang="ts">
import {useSessionStore} from '../../../stores/session'
const session=useSessionStore()
import {onMounted,ref} from 'vue'
import {systemApi} from '../../../api/system'
import {bytes,date,errorText} from '../../../utils/format'
import type {StorageUsage,StorageIssues} from '../../../types/api'
import UiButton from '../../../components/ui/UiButton.vue'
import StorageInventory from '../StorageInventory.vue'
import HostAudit from '../HostAudit.vue'
defineProps<{usage:StorageUsage|null}>()
const emit=defineEmits<{(e:'refresh'):void}>()
const page=ref<StorageIssues|null>(null),loading=ref(false),requesting=ref(false),error=ref(''),message=ref(''),inventory=ref(false),host=ref(false)
async function load(offset=0){
  if(loading.value)return
  loading.value=true;error.value=''
  try{page.value=await systemApi.storageIssues(offset)}
  catch(e){error.value=errorText(e)}finally{loading.value=false}
}
async function reconcile(){
  requesting.value=true;error.value='';message.value=''
  try{await systemApi.reconcile();message.value='Дополнительная сверка поставлена в очередь фоновой службы.';emit('refresh')}
  catch(e){error.value=errorText(e)}finally{requesting.value=false}
}
onMounted(()=>void load())
const issues:Record<string,string>={unclassified_path:'Неизвестный путь',owner_mismatch:'Неверный владелец',run_batch_mismatch:'Неверная связь с ФО',missing_result_media:'Отсутствует результат',invalid_result_manifest:'Повреждённый манифест',unlisted_result_media:'Файл не указан в манифесте',expected_not_observed:'Ожидаемый файл не найден',size_mismatch:'Размер не совпадает',incomplete_publication:'Незавершённая публикация',leftover_finalized_part:'Остаток завершённой загрузки',part_receipt_size_mismatch:'Размер загрузки не совпадает'}
</script>
<template>
  <div class="stack">
    <section class="panel stack">
      <h2>Сверка и расхождения</h2>
      <div class="grid2">
        <div><span class="meta">Последняя сверка</span><h3>{{date(usage?.registry?.reconciled_at)}}</h3></div>
        <div><span class="meta">Последнее измерение</span><h3>{{date(usage?.registry?.sampled_at)}}</h3></div>
        <div><span class="meta">Ожидаемых файлов не найдено</span><h3>{{usage?.registry?.missing_expected??'—'}}</h3></div>
        <div><span class="meta">Изменений ожидают учёта</span><h3>{{usage?.registry?.pending_changes??'—'}}</h3></div>
      </div>
      <p class="meta">Сверка выполняется в фоне, не удаляет файлы и не блокирует страницу. Ошибок обхода: {{usage?.registry?.errors??'—'}}. Конфликтов inode между владельцами: {{usage?.registry?.cross_owner_inode_conflicts??'—'}}.</p>
      <div class="row wrap">
        <UiButton v-if="session.can('storage.check')" :loading="requesting" :disabled="usage?.registry?.reconciliation_requested" @click="reconcile">Запустить сверку</UiButton>
        <UiButton :loading="loading" @click="load(0)">Обновить расхождения</UiButton>
      </div>
      <p v-if="message" role="status" class="meta">{{message}}</p>
      <p v-if="error" role="alert" class="alert error">{{error}}</p>
      <div v-for="(n,key) in usage?.registry?.issues||{}" :key="key" class="row between wrap"><span>{{issues[key]||key}}</span><strong>{{n}}</strong></div>
      <h3>Обнаруженные файлы</h3>
      <p v-if="page&&!page.files.length" class="meta">На этой странице расхождений нет.</p>
      <div v-for="(row,i) in page?.files||[]" :key="row.path+i" class="stack issue-row"><div class="row between wrap"><strong>{{issues[row.issue]||row.issue}}</strong><span>{{bytes(row.logical_bytes)}}</span></div><code>{{row.path}}</code></div>
      <h3>Отсутствующие файлы</h3>
      <div v-for="row in page?.missing||[]" :key="row.path" class="issue-row"><code>{{row.path}}</code></div>
      <p v-if="page&&!page.missing.length" class="meta">На этой странице отсутствующих файлов нет.</p>
      <div v-if="page" class="row between wrap"><span class="meta">Смещение {{page.offset}} · снимок {{date(page.snapshot)}}</span><div class="row"><UiButton small :disabled="loading||page.offset===0" @click="load(Math.max(0,page.offset-page.limit))">Назад</UiButton><UiButton small :disabled="loading||(page.files.length<page.limit&&page.missing.length<page.limit)" @click="load(page.offset+page.limit)">Дальше</UiButton></div></div>
      <details v-if="usage?.host?.unknown_sample?.length"><summary>Неизвестные файлы хоста (выборка)</summary><div v-for="row in usage.host.unknown_sample" :key="row.path" class="issue-row"><code>{{row.path}}</code> · {{bytes(row.logical_bytes)}}</div></details>
      <p class="meta">Неизвестные файлы не удаляются автоматически.</p>
    </section>
    <section class="panel stack"><h2>Подробные отчёты</h2><p class="meta">Снимок реестра и исторический диагностический аудит; не дополнительные источники итоговых размеров.</p>
      <UiButton v-if="session.can('storage.check')" @click="inventory=!inventory">{{inventory?'Скрыть реестр файлов':'Открыть реестр файлов'}}</UiButton>
      <UiButton @click="host=!host">{{host?'Скрыть отчёт хоста':'Открыть отчёт хоста'}}</UiButton>
    </section>
    <StorageInventory v-if="inventory"/>
    <section v-if="host" aria-label="Аудит сервера"><HostAudit/></section>
  </div>
</template>
<style scoped>.issue-row{border-bottom:1px solid var(--border-subtle);padding:10px 0;gap:4px;min-width:0}code{overflow-wrap:anywhere;white-space:normal;font-size:12px}summary{cursor:pointer}</style>
