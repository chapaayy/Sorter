<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {systemApi} from '../../../api/system'
import {bytes,date,errorText} from '../../../utils/format'
import {usePolling} from '../../../composables/usePolling'
import type {MaintenanceKind,StorageMaintenance,StoragePreview} from '../../../types/api'
import UiButton from '../../../components/ui/UiButton.vue'
import ConfirmDialog from '../../../components/ui/ConfirmDialog.vue'
import StorageSettings from '../../settings/StorageSettings.vue'
const emit=defineEmits<{(e:'refresh'):void}>()
const actions:{kind:MaintenanceKind;title:string;description:string}[]=[
 {kind:'expired_archives',title:'Просроченные ZIP',description:'Только архивы и служебные фрагменты с истёкшим сроком и без активного скачивания или сборки.'},
 {kind:'unused_thumbnails',title:'Неиспользуемые миниатюры',description:'Только миниатюры без владельцев и зависимостей, после защитного срока.'},
 {kind:'abandoned_scratch',title:'Аварийные временные файлы',description:'Только распознанные завершённые или аварийные scratch и загрузки моделей после защитного срока и проверки блокировки.'}
]
const statuses=ref<StorageMaintenance[]>([]),preview=ref<StoragePreview|null>(null),loading=ref(false),busy=ref(false),error=ref('')
const names:Record<string,string>={queued:'В очереди',running:'Выполняется',completed:'Завершено',failed:'Ошибка',interrupted:'Прервано'}
const state=(kind:MaintenanceKind)=>statuses.value.find(s=>s.kind===kind)
const active=(kind:MaintenanceKind)=>['queued','running'].includes(state(kind)?.state||'')
async function refresh(){
  if(loading.value)return
  loading.value=true
  try{
    const previous=statuses.value
    statuses.value=await systemApi.maintenance()
    if(statuses.value.some(s=>s.state==='completed'&&previous.find(p=>p.kind===s.kind)?.finished_at!==s.finished_at))emit('refresh')
    error.value=''
  }catch(e){error.value=errorText(e)}finally{loading.value=false}
}
async function inspect(kind:MaintenanceKind){
  busy.value=true;error.value=''
  try{preview.value=await systemApi.maintenancePreview(kind)}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function execute(){
  if(!preview.value)return
  busy.value=true
  try{const row=await systemApi.maintenanceStart(preview.value.kind);statuses.value=[...statuses.value.filter(s=>s.kind!==row.kind),row];preview.value=null;error.value=''}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
onMounted(()=>void refresh())
usePolling(refresh,5000)
</script>
<template>
<div class="stack">
  <section class="panel stack">
    <div class="row between wrap"><h2>Безопасное обслуживание</h2><UiButton :loading="loading" @click="refresh">Обновить состояние</UiButton></div>
    <p class="meta">Операции идут в фоне по действующим правилам. Перед удалением проверяются актуальные зависимости и блокировки. Неизвестные файлы, оригиналы, постоянные эмбеддинги и рабочая модель защищены.</p>
    <p v-if="error" role="alert" class="alert error">{{error}}</p>
    <div v-for="action in actions" :key="action.kind" class="stack action">
      <div class="row between wrap"><h3>{{action.title}}</h3><UiButton :disabled="busy||active(action.kind)" @click="inspect(action.kind)">Предпросмотр очистки</UiButton></div>
      <p class="meta">{{action.description}}</p>
      <p v-if="state(action.kind)" role="status" class="meta">{{names[state(action.kind)!.state]}} · {{date(state(action.kind)?.finished_at||state(action.kind)?.requested_at)}}<template v-if="state(action.kind)?.removed!=null"> · обработано объектов: {{state(action.kind)?.removed}}</template></p>
    </div>
    <details><summary>Технический кэш и закрытые журналы</summary><p class="meta">Технический кэш Torch/HF/XDG допускает удаление только в отдельном офлайн-режиме с остановленными процессами и проверенной независимостью модели. Онлайн-очистка не разрешена. Закрытые журналы ротируются автоматически существующими службами; PostgreSQL, сертификаты и используемые журналы не удаляются из этого раздела.</p></details>
  </section>
  <StorageSettings/>
  <ConfirmDialog v-if="preview" title="Подтвердить безопасную очистку" :message="'Кандидатов по возрасту: '+preview.files+' · '+bytes(preview.allocated_bytes)+' на диске. Снимок: '+date(preview.sampled_at)+(preview.partial?' (неполный).':'.')+' Это предварительная оценка, не обещание освободить указанное место. Будут удалены только объекты, прошедшие повторную проверку правил и блокировок.'" confirm-label="Запустить очистку" :busy="busy" @cancel="preview=null" @confirm="execute"/>
</div>
</template>
<style scoped>.action{padding:12px 0;border-bottom:1px solid var(--border-subtle);gap:6px}summary{cursor:pointer}</style>
