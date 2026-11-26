<script setup lang="ts">
import {useSessionStore} from '../../../stores/session'
const session=useSessionStore()
import {computed,onMounted,ref} from 'vue'
import {systemApi} from '../../../api/system'
import {bytes,date,errorText} from '../../../utils/format'
import {usePolling} from '../../../composables/usePolling'
import type {MaintenanceKind,HostMaintenanceKind,MapUpdateStatus,StorageMaintenance,StoragePreview} from '../../../types/api'
import UiButton from '../../../components/ui/UiButton.vue'
import ConfirmDialog from '../../../components/ui/ConfirmDialog.vue'
import StorageSettings from '../../settings/StorageSettings.vue'
const emit=defineEmits<{(e:'refresh'):void}>()
const actions:{kind:MaintenanceKind;title:string;description:string}[]=[
 {kind:'expired_archives',title:'Просроченные ZIP',description:'Только архивы и служебные фрагменты с истёкшим сроком и без активного скачивания или сборки.'},
 {kind:'unused_thumbnails',title:'Неиспользуемые миниатюры',description:'Только миниатюры без владельцев и зависимостей, после защитного срока.'},
 {kind:'abandoned_scratch',title:'Аварийные временные файлы',description:'Только распознанные аварийные файлы после защитного срока и проверки блокировки.'}
]
const hostActions:{kind:HostMaintenanceKind;title:string;description:string}[]=[
 {kind:'storage-cache',title:'Удаляемый технический кэш',description:'Только разрешённые кэши Torch, Hugging Face и XDG. Рабочая модель, постоянные эмбеддинги и миниатюры не затрагиваются. Сайт временно остановится; при активных задачах операция отменится.'},
 {kind:'storage-logs',title:'Закрытые журналы PostgreSQL',description:'Штатная ротация только закрытых сегментов сверх действующего бюджета; активные журналы и данные БД защищены.'}
]
const statuses=ref<StorageMaintenance[]>([]),host=ref<MapUpdateStatus|null>(null),hostError=ref(''),preview=ref<StoragePreview|null>(null),loading=ref(false),busy=ref(false),error=ref('')
const names:Record<string,string>={queued:'В очереди',running:'Выполняется',completed:'Завершено',failed:'Ошибка',interrupted:'Прервано'}
const state=(kind:MaintenanceKind)=>statuses.value.find(s=>s.kind===kind)
const active=(kind:MaintenanceKind)=>['queued','running'].includes(state(kind)?.state||'')
const isHost=(kind:MaintenanceKind|HostMaintenanceKind):kind is HostMaintenanceKind=>kind==='storage-cache'||kind==='storage-logs'
const hostReady=computed(()=>!!host.value?.available&&!!host.value.storage_maintenance_supported&&!host.value.busy&&host.value.phase!=='recovery_required'&&!hostError.value)
const signed=(n:number)=> (n<0?'−':'+')+bytes(Math.abs(n))
const message=computed(()=>{
 const row=preview.value
 if(!row)return ''
 const estimate=row.kind==='storage-logs'?'Логический объём сверх бюджета: '+bytes(row.logical_excess_bytes):row.kind==='storage-cache'?'Учтённый технический кэш: '+bytes(row.allocated_bytes):'Кандидатов по возрасту: '+row.files+' · '+bytes(row.allocated_bytes)+' на диске.'
 return estimate+' Снимок: '+date(row.sampled_at)+(row.partial?' (неполный).':'.')+' Это предварительная оценка, не обещание освободить указанное место. '+(row.kind==='storage-cache'?'Приложение будет временно остановлено. При активной работе или отсутствии необходимых гарантий очистка отменится.':'Перед удалением повторно проверяются правила и блокировки.')
})
async function refresh(){
 if(loading.value||busy.value||!session.can('storage.maintenance'))return
 loading.value=true
 try{
  const previous=statuses.value
  statuses.value=await systemApi.maintenance()
  if(statuses.value.some(s=>s.state==='completed'&&previous.find(p=>p.kind===s.kind)?.finished_at!==s.finished_at))emit('refresh')
  error.value=''
 }catch(e){error.value=errorText(e)}
 try{
  const previous=host.value?.storage_action
  if(!session.can('system.update_status'))return
  host.value=await systemApi.updateStatus()
  hostError.value=''
  if(host.value.storage_action?.state==='completed'&&previous?.finished_at!==host.value.storage_action.finished_at)emit('refresh')
 }catch(e){hostError.value=errorText(e)}finally{loading.value=false}
}
async function inspect(kind:MaintenanceKind|HostMaintenanceKind){
 busy.value=true;error.value=''
 try{preview.value=await (isHost(kind)?systemApi.hostMaintenancePreview(kind):systemApi.maintenancePreview(kind))}
 catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function execute(){
 if(!preview.value)return
 busy.value=true
 try{
  const kind=preview.value.kind
  if(isHost(kind))host.value=await systemApi.hostMaintenanceStart(kind)
  else{const row=await systemApi.maintenanceStart(kind);statuses.value=[...statuses.value.filter(s=>s.kind!==row.kind),row]}
  preview.value=null;error.value=''
 }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
onMounted(()=>void refresh())
usePolling(refresh,5000)
</script>
<template>
<div class="stack">
 <section v-if="session.can('storage.maintenance')" class="panel stack">
  <div class="row between wrap"><h2>Безопасное обслуживание</h2><UiButton :loading="loading" @click="refresh">Обновить состояние</UiButton></div>
  <p class="meta">Операции идут по действующим правилам. Перед удалением проверяются зависимости и блокировки. Неизвестные файлы, оригиналы, постоянные эмбеддинги и рабочая модель защищены.</p>
  <p v-if="error" role="alert" class="alert error">{{error}}</p>
  <div v-for="action in actions" :key="action.kind" class="stack action">
   <div class="row between wrap"><h3>{{action.title}}</h3><UiButton :disabled="busy||loading||active(action.kind)" @click="inspect(action.kind)">Предпросмотр очистки</UiButton></div>
   <p class="meta">{{action.description}}</p>
   <p v-if="state(action.kind)" role="status" class="meta">{{names[state(action.kind)!.state]}} · {{date(state(action.kind)?.finished_at||state(action.kind)?.requested_at)}}<template v-if="state(action.kind)?.removed!=null"> · обработано объектов: {{state(action.kind)?.removed}}</template><template v-if="state(action.kind)?.available_delta_bytes!=null"> · изменение свободного места: {{signed(state(action.kind)!.available_delta_bytes!)}}</template></p>
  </div>
  <details v-if="session.can('system.update_status')"><summary>Технический кэш и закрытые журналы</summary>
   <p v-if="!hostReady" class="meta">{{hostError?'Хостовая служба временно недоступна.':host?.busy?'Хостовая операция выполняется.':host?.phase==='recovery_required'?'Требуется восстановление сервисов.':'Хостовое обслуживание недоступно.'}}</p>
   <div v-for="action in hostActions" :key="action.kind" class="stack action">
    <div class="row between wrap"><h3>{{action.title}}</h3><UiButton :disabled="!hostReady||busy||loading" @click="inspect(action.kind)">Предпросмотр: {{action.title}}</UiButton></div>
    <p class="meta">{{action.description}}</p>
    <p v-if="host?.storage_action?.kind===action.kind" role="status" class="meta">{{names[host.storage_action.state]}} · {{host.storage_action.detail||''}}<template v-if="host.storage_action.available_delta_bytes!=null"> · изменение свободного места: {{signed(host.storage_action.available_delta_bytes)}}</template></p>
   </div>
  </details>
  <p class="meta">Изменение свободного места — наблюдение до/после, включая параллельные записи, а не гарантированно освобождённые байты.</p>
 </section>
 <StorageSettings v-if="session.can('system.retention_view')"/>
 <ConfirmDialog v-if="preview" title="Подтвердить безопасную очистку" :message="message" confirm-label="Запустить очистку" :busy="busy" @cancel="preview=null" @confirm="execute"/>
</div>
</template>
<style scoped>.action{padding:12px 0;border-bottom:1px solid var(--border-subtle);gap:6px}summary{cursor:pointer}</style>
