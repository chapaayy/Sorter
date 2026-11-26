<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {systemApi} from '../../../api/system'
import {errorText} from '../../../utils/format'
import UiButton from '../../../components/ui/UiButton.vue'
import {bytes,date} from '../../../utils/format'
import type {StorageUsage,PhysicalTreeBucket,RootDiskSample} from '../../../types/api'
const props=defineProps<{usage:StorageUsage|null;failed?:boolean}>()
const emit=defineEmits<{(e:'refresh'):void}>()
const requesting=ref(false),requestError=ref(''),accepted=ref(false)
const checking=computed(()=>['queued','running','retry'].includes(props.usage?.independent_check?.state||''))
watch(()=>props.usage?.independent_check?.state,state=>{if(state)accepted.value=false})
async function check(){
  requesting.value=true;requestError.value='';accepted.value=false
  try{await systemApi.independentCheck();accepted.value=true;emit('refresh')}
  catch(e){requestError.value=errorText(e)}finally{requesting.value=false}
}
const tree=computed(()=>props.usage?.host?.tree_check)
const disk=computed(()=>props.usage?.host?.disk_check)
const history=computed(()=>[...(props.usage?.host?.tree_history||[])].reverse())
const diskHistory=computed(()=>[...(props.usage?.host?.disk_history||[])].reverse())
const stale=computed(()=>!!props.failed||!!props.usage?.host?.stale)
const complete=computed(()=>!stale.value&&!props.usage?.host?.partial&&!tree.value?.stale&&!tree.value?.partial&&!!tree.value?.comparable&&tree.value.absolute_discrepancy_bytes!=null)
const old=computed(()=>history.value.find(r=>r.finished_at!==tree.value?.finished_at&&r.comparable&&r.absolute_discrepancy_bytes!=null))
const growth=computed(()=>complete.value&&old.value?.absolute_discrepancy_bytes!=null?tree.value!.absolute_discrepancy_bytes!-old.value.absolute_discrepancy_bytes:null)
const exact=(n?:number|null)=>n==null||!Number.isFinite(n)?'—':new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(n)+' Б'
const mapped=computed(()=>tree.value?.registry_file_bytes!=null&&tree.value.host_file_bytes!=null&&tree.value.directory_bytes!=null?tree.value.registry_file_bytes+tree.value.host_file_bytes+tree.value.directory_bytes:null)
const names={map_storage:'Хранилище MAP',docker_engine:'Docker — физические файлы',containerd_default:'containerd — стандартный путь',system_logs:'Системные журналы',other_visible:'Другие видимые файлы хоста'} as const
const diskRows=computed(()=>Object.entries(names).flatMap(([key,label])=>{
  const row=disk.value?.[key as keyof RootDiskSample] as PhysicalTreeBucket|undefined
  return row&&typeof row.file_bytes==='number'?[{key,label,amount:row.file_bytes+row.directory_bytes}]:[]
}))
</script>
<template>
  <div class="stack control">
    <section class="panel stack">
      <div class="row between wrap"><h2>Побайтовый контроль MAP</h2><UiButton :loading="requesting" :disabled="checking" @click="check">Проверить учёт</UiButton></div>
      <p v-if="checking" class="meta" role="status">{{usage?.independent_check?.state==='retry'?usage.independent_check.detail:'Проверка учёта…'}}</p>
      <p v-else-if="accepted" class="meta" role="status">Запрос принят фоновой службой.</p>
      <p v-if="requestError" class="alert error" role="alert">{{requestError}}</p>
      <p class="meta">Независимый обход storage/ с физическими блоками каталогов. Замер раз в час; неполный повторяется через 5 минут. Это не атомарный снимок работающей файловой системы.</p>
      <p v-if="!tree" class="meta">Ожидаем первый независимый замер.</p>
      <template v-else>
        <p v-if="!complete" :class="checking&&!tree.errors?'meta':'alert warning'" role="status">Нет сопоставимого актуального замера. Нули и 100% не подставляются.</p>
        <p v-else-if="tree.absolute_discrepancy_bytes!==0" class="alert warning" role="status">Обнаружено расхождение физических байтов.</p>
        <p v-else class="meta" role="status">Последний сопоставимый замер: расхождение 0 байт.</p>
        <p v-if="complete&&tree.absolute_discrepancy_bytes===0" class="meta">100% совпадение физических байтов по этому замеру.</p>
        <div class="metrics">
          <div><span class="meta">Независимый размер дерева</span><strong>{{exact(tree.allocated_bytes)}}</strong><span class="meta">{{bytes(tree.allocated_bytes)}}</span></div>
          <div><span class="meta">Учтено с блоками каталогов</span><strong>{{exact(mapped)}}</strong><span class="meta">Реестр + хостовые файлы + каталоги</span></div>
          <div><span class="meta">Абсолютное расхождение</span><strong>{{complete?exact(tree.absolute_discrepancy_bytes):'—'}}</strong><span class="meta">Раздельные остатки не компенсируют друг друга</span></div>
          <div><span class="meta">Изменение расхождения</span><strong>{{exact(growth)}}</strong><span class="meta">Относительно прошлого сопоставимого замера</span></div>
        </div>
        <div v-if="growth!=null&&growth>0" class="alert warning" role="status">Необъяснённое расхождение выросло на {{exact(growth)}}.</div>
        <div class="row between wrap"><span>Блоки каталогов (не личная квота)</span><strong>{{exact(tree.directory_bytes)}}</strong></div>
        <div class="row between wrap"><span>Приложение · знаковый остаток</span><strong>{{exact(tree.app_delta_bytes)}}</strong></div>
        <div class="row between wrap"><span>Инфраструктура · знаковый остаток</span><strong>{{exact(tree.host_delta_bytes)}}</strong></div>
        <div class="row between wrap"><span>Неопознанные объекты при замере</span><strong>{{tree.unknown_files??'—'}} · {{exact(tree.unknown_bytes)}}</strong></div>
        <p v-if="(tree.unknown_files??0)>0" class="alert warning">Есть неопознанные объекты. Подробности — в диагностике. Автоматически не удаляются.</p>
        <p class="meta">Замер: {{date(tree.finished_at)}} · объектов: {{tree.entries??'—'}} · ошибок: {{tree.errors}} · изменившихся каталогов: {{tree.changed_directories??'—'}} · другие устройства: {{tree.other_devices??'—'}} · пересечение областей hardlink: {{tree.cross_scope_links??'—'}}<span v-if="tree.limit_reached"> · достигнут предел обхода</span>.</p>
      </template>
    </section>
    <section class="panel stack">
      <h2>Корневая файловая система сервера</h2>
      <p class="meta">Отдельный замер раз в 6 часов; неполный повторяется через час. Только видимые пути на устройстве корня; другие файловые системы и смонтированные представления контейнеров не обходятся. Виртуальные размеры образов Docker не прибавляются повторно.</p>
      <p v-if="!disk" class="meta">Ожидаем первый замер корневой ФС.</p>
      <template v-else>
        <p v-if="!disk.comparable||stale||disk.stale" class="alert warning">Замер неполный или диск изменялся. Разбивка предварительная.</p>
        <div v-for="row in diskRows" :key="row.key" class="row between wrap"><span>{{row.label}}<small v-if="disk.paths?.[row.key]" class="meta path">{{disk.paths[row.key]}}</small></span><strong>{{exact(row.amount)}}</strong></div>
        <div class="row between wrap"><span>Всего видимых выделенных блоков</span><strong>{{exact(disk.allocated_bytes)}}</strong></div>
        <div class="row between wrap"><span>Удалённые открытые файлы (нижняя оценка)</span><strong>{{exact(disk.deleted_open?.allocated_bytes)}}</strong></div>
        <div class="row between wrap"><span>Занято по счётчику ядра</span><strong>{{exact(disk.capacity_after?.used_bytes)}}</strong></div>
        <div class="row between wrap"><span>Остаток после измеренных путей и открытых файлов</span><strong>{{exact(disk.residual_bytes)}}</strong></div>
        <p class="meta">Остаток не объявляется расходом ОС: возможны скрытые mountpoint-пути, внутренние блоки ФС, mmap и несинхронность. Размеры на другом устройстве не входят в этот замер. ФС: {{disk.filesystem||'—'}} · устройство: {{disk.device||'—'}} · исключено mountpoint: {{disk.excluded_mounts??'—'}} · {{date(disk.finished_at)}}.</p>
      </template>
    </section>
    <section class="panel stack">
      <h2>История измерений</h2>
      <p class="meta">До 336 последних замеров MAP и 64 замеров корневого диска. Неполные значения не превращаются в нули.</p>
      <p v-if="!history.length" class="meta">Истории пока нет.</p>
      <div v-for="row in history.slice(0,20)" :key="row.finished_at" class="history-row">
        <span>{{date(row.finished_at)}}</span><span class="meta">{{exact(row.allocated_bytes)}} · неизвестно: {{exact(row.unknown_bytes)}}</span><strong>{{row.comparable?exact(row.absolute_discrepancy_bytes):'Неполный замер'}}</strong>
      </div>
      <details v-if="history.length>20"><summary>Остальные замеры MAP</summary><div v-for="row in history.slice(20)" :key="row.finished_at" class="history-row"><span>{{date(row.finished_at)}}</span><span class="meta">{{exact(row.allocated_bytes)}}</span><strong>{{row.comparable?exact(row.absolute_discrepancy_bytes):'Неполный замер'}}</strong></div></details>
      <details v-if="diskHistory.length"><summary>История корневой ФС</summary><div v-for="row in diskHistory" :key="row.finished_at" class="history-row"><span>{{date(row.finished_at)}}</span><span class="meta">Видимые: {{exact(row.allocated_bytes)}}</span><strong>{{row.comparable?exact(row.residual_bytes):'Предварительно'}}</strong></div></details>
    </section>
  </div>
</template>
<style scoped>
.control{min-width:0}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.metrics>div{display:grid;gap:6px;min-width:0;padding:12px;background:var(--panel-alt);border-radius:10px}.metrics strong{font-size:20px;overflow-wrap:anywhere}.history-row{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;border-bottom:1px solid var(--border-subtle);padding:8px 0}.path{display:block;overflow-wrap:anywhere}summary{cursor:pointer}.row strong{overflow-wrap:anywhere}@media(max-width:520px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.metrics strong{font-size:16px}}
</style>
