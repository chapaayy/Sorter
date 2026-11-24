<script setup lang="ts">
import {onMounted,ref} from 'vue'
import type {StorageRegistry,StorageOperations} from '../../../types/api'
import {systemApi} from '../../../api/system'
import {bytes,date,errorText} from '../../../utils/format'
import {usePolling} from '../../../composables/usePolling'
import {categoryName} from './labels'
import UiButton from '../../../components/ui/UiButton.vue'
defineProps<{registry?:StorageRegistry}>()
const data=ref<StorageOperations|null>(null),error=ref(''),loading=ref(false)
async function refresh(){
  if(loading.value)return
  loading.value=true
  try{data.value=await systemApi.storageOperations();error.value=''}
  catch(e){error.value=errorText(e)}finally{loading.value=false}
}
onMounted(()=>void refresh())
usePolling(refresh,15000)
</script>
<template>
  <section class="panel stack">
    <div class="row between wrap"><h2>Временное хранилище</h2><UiButton :loading="loading" @click="refresh">Обновить операции</UiButton></div>
    <p v-if="error" role="alert" class="alert error">{{error}}</p>
    <div class="grid2">
      <div><span class="meta">На диске</span><h3>{{bytes(registry?.temporary?.allocated_bytes)}}</h3></div>
      <div><span class="meta">Зарезервировано операциями</span><h3>{{bytes(registry?.reserved_bytes)}}</h3></div>
      <div><span class="meta">Наблюдавшийся пик</span><h3>{{bytes(registry?.temporary_peak_bytes)}}</h3></div>
      <div><span class="meta">Логический размер</span><h3>{{bytes(registry?.temporary?.logical_bytes)}}</h3></div>
    </div>
    <p class="meta">Резервы и остаток загрузок — будущие байты, не прибавляются к занятому месту. Пик наблюдаемый, не точный максимум между измерениями.</p>
    <h3>Незавершённые загрузки</h3>
    <div class="row between wrap"><span>ФО: {{registry?.unfinished_fo?.files??'—'}} файлов</span><strong>Осталось {{bytes(registry?.unfinished_fo?.remaining_bytes)}}</strong></div>
    <div class="row between wrap"><span>Образцы: {{registry?.unfinished_references?.files??'—'}} файлов</span><strong>Осталось {{bytes(registry?.unfinished_references?.remaining_bytes)}}</strong></div>
    <p class="meta">Следующий возможный срок проверки ФО: {{date(data?.unfinished_fo_next_eligible_at)}}. Незавершённые загрузки защищены действующими операциями; срок без активности — 30 дней.</p>
    <h3>Активные операции</h3>
    <p v-if="data&&!data.cleanup_worker.alive" class="alert warning" role="status">Нет свежего сигнала службы очистки.</p>
    <div v-for="row in data?.active_queue||[]" :key="row.seq" class="row between wrap"><span>{{categoryName(row.kind)}}<small v-if="row.display_name" class="meta"> · {{row.display_name}}</small></span><span class="meta">Начало {{date(row.started_at)}}</span></div>
    <div v-for="(row,key) in registry?.reservations||{}" :key="key" class="row between wrap"><span>{{categoryName(key)}} · резервов {{row.operations}}</span><strong>{{bytes(row.bytes)}}</strong></div>
    <p v-if="data&&!data.active_queue.length&&!Object.keys(registry?.reservations||{}).length" class="meta">Активных задач очереди и наблюдаемых резервов нет.</p>
    <h3>ZIP-архивы</h3>
    <div v-for="row in data?.archives||[]" :key="row.category" class="stack item">
      <div class="row between wrap"><strong>{{categoryName(row.category)}}</strong><span>{{row.files}} готовых · {{row.expired}} просрочено</span></div>
      <span class="meta">Ближайшая возможная очистка: {{date(row.next_eligible_at)}}</span>
    </div>
    <p v-if="data&&!data.archives.length" class="meta">Готовых ZIP в реестре нет.</p>
    <p class="meta">ZIP удаляются после {{data?data.archive_ttl_seconds/60+' мин':'истечения TTL'}} с публикации, только когда не используются. Аварийный scratch — после {{data?data.scratch_grace_seconds/60+' мин':'защитного срока'}} и проверки блокировки.</p>
    <details>
      <summary>Наблюдаемые временные файлы ({{registry?.temporary_operations?.total_groups??'—'}} групп)</summary>
      <div v-for="row in registry?.temporary_operations?.rows||[]" :key="row.operation_key+row.category" class="stack item">
        <div class="row between wrap"><strong>{{categoryName(row.category)}}</strong><strong>{{bytes(row.allocated_bytes)}}</strong></div>
        <code>{{row.operation_key}}</code><span class="meta">{{row.files}} файлов · {{bytes(row.logical_bytes)}} логически</span>
      </div>
      <p v-if="registry?.temporary_operations?.partial" class="meta">Показаны 100 крупнейших групп, общий объём включает остальные.</p>
    </details>
  </section>
</template>
<style scoped>.item{padding:10px 0;border-bottom:1px solid var(--border-subtle);gap:4px}code{overflow-wrap:anywhere;white-space:normal;font-size:12px}summary{cursor:pointer}</style>
