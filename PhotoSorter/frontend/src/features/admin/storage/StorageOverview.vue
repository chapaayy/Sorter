<script setup lang="ts">
import {computed} from 'vue'
import {bytes,date} from '../../../utils/format'
import type {StorageUsage,StorageCounter} from '../../../types/api'
import CategoryTable from './CategoryTable.vue'
import {groups} from './labels'
const props=defineProps<{usage:StorageUsage}>()
const registry=computed(()=>props.usage.registry)
const host=computed(()=>props.usage.host)
const hostKnown=computed(()=>!!host.value?.at&&!host.value.partial&&!host.value.stale)
const categories=computed(()=>{
  const all:Record<string,StorageCounter>={...registry.value?.categories}
  for(const [key,row] of Object.entries(host.value?.categories||{})){
    const prev=all[key]
    all[key]=prev?{allocated_bytes:prev.allocated_bytes+row.allocated_bytes,logical_bytes:prev.logical_bytes+row.logical_bytes,files:prev.files+row.files,hardlink_paths:prev.hardlink_paths+row.hardlink_paths}:row
  }
  return all
})
const hostTotal=computed(()=>host.value?Object.values(host.value.categories||{}).reduce((n,r)=>n+r.allocated_bytes,0):null)
const mapTotal=computed(()=>registry.value?.allocated_bytes==null?null:registry.value.allocated_bytes+(hostTotal.value??0))
const mapLogical=computed(()=>registry.value?.logical_bytes==null?null:registry.value.logical_bytes+Object.values(host.value?.categories||{}).reduce((n,r)=>n+r.logical_bytes,0))
const filesystems=computed(()=>Object.entries(props.usage.filesystems||{[String(props.usage.disk.device??'app')]:props.usage.disk}))
const groupTotals=computed(()=>groups.map(g=>({...g,value:g.keys.reduce((n,k)=>n+(categories.value[k]?.allocated_bytes||0),0)})))
const remainder=computed(()=>Object.keys(categories.value).filter(k=>!groups.some(g=>g.keys.includes(k))))
const pct=(n:number,total:number)=>total>0?Math.max(0,Math.min(100,n/total*100)):0
const groupColors=['#5679bc','#43a18b','#d59749','#9374c9','#84909f']
function mapped(fs:{map_allocated_bytes?:number|null;used_bytes:number}){return fs.map_allocated_bytes!=null&&fs.map_allocated_bytes>=0&&fs.map_allocated_bytes<=fs.used_bytes?fs.map_allocated_bytes:null}
</script>
<template>
  <div class="stack">
    <section class="panel stack">
      <div class="row between wrap"><h2>Объём хранилища</h2><span class="meta">Физические блоки, без повторного учёта hardlink</span></div>
      <div class="metrics">
        <div><span class="meta">Всего · диск приложения</span><strong>{{bytes(usage.disk.total_bytes)}}</strong></div>
        <div><span class="meta">Занято</span><strong>{{bytes(usage.disk.used_bytes)}}</strong></div>
        <div><span class="meta">Свободно для записи</span><strong>{{bytes(usage.disk.available_bytes)}}</strong></div>
        <div><span class="meta">Учтено MAP{{!hostKnown||registry?.partial?' (частично)':''}}</span><strong>{{bytes(mapTotal)}}</strong></div>
      </div>
      <div v-for="[key,fs] in filesystems" :key="key" class="stack disk">
        <div class="row between wrap"><strong>{{key===String(usage.disk.device)||filesystems.length===1?'Диск приложения':'Файловая система '+key}}</strong><span class="meta">{{bytes(fs.used_bytes)}} / {{bytes(fs.total_bytes)}}</span></div>
        <div class="disk-bar" role="img" :aria-label="'Занято '+bytes(fs.used_bytes)+', доступно '+bytes(fs.available_bytes)">
          <template v-if="mapped(fs)!==null">
            <span class="seg map" :style="{width:pct(mapped(fs)??0,fs.total_bytes)+'%'}"/>
            <span class="seg other" :style="{width:pct(fs.used_bytes-(mapped(fs)??0),fs.total_bytes)+'%'}"/>
          </template>
          <span v-else class="seg other" :style="{width:pct(fs.used_bytes,fs.total_bytes)+'%'}"/>
          <span class="seg free" :style="{width:pct(fs.available_bytes,fs.total_bytes)+'%'}"/>
        </div>
        <div class="legend">
          <span><i class="map"/>MAP: {{bytes(fs.map_allocated_bytes)}}</span>
          <span><i class="other"/>Вне MAP / расхождение: {{fs.outside_map_or_unexplained_bytes!=null&&fs.outside_map_or_unexplained_bytes<0?'−'+bytes(Math.abs(fs.outside_map_or_unexplained_bytes)):bytes(fs.outside_map_or_unexplained_bytes)}}<template v-if="(fs.outside_map_or_unexplained_bytes??0)<0"> (несинхронные замеры)</template></span>
          <span><i class="free"/>Свободно: {{bytes(fs.available_bytes)}}</span>
        </div>
        <p v-if="mapped(fs)===null&&fs.map_allocated_bytes!=null" class="meta">Разбивка диска временно несогласована. Не подменяем расхождение нулём.</p>
      </div>
      <div class="metrics smaller">
        <div><span class="meta">MAP по файлам (логически)</span><strong>{{bytes(mapLogical)}}</strong></div>
        <div><span class="meta">Резерв диска (действующий)</span><strong>{{bytes(usage.disk.reserved_bytes)}}</strong></div>
        <div v-if="usage.disk.operation_reserved_bytes!=null"><span class="meta">Резервы активных операций</span><strong>{{bytes(usage.disk.operation_reserved_bytes)}}</strong></div>
        <div><span class="meta">Доступно для новых операций</span><strong>{{bytes(usage.disk.allocatable_bytes)}}</strong></div>
      </div>
      <p class="meta">Измерение хоста: {{date(host?.at)}}. <span v-if="usage.disk.warning">Внимание: мало свободного места. </span>Docker и остальные данные входят в «Вне MAP / расхождение», но не суммируются с MAP повторно. Разница также включает метаданные ФС и несинхронность выборок. Свободные блоки, зарезервированные ФС, не входят в доступное место.</p>
      <p v-if="!host||host.stale||host.partial" class="alert warning" role="status">Хостовый учёт {{!host?'ещё недоступен':host.stale?'устарел':'неполный'}}. Размер инфраструктуры и общий объём MAP предварительные.</p>
    </section>
    <section class="panel stack">
      <h2>Распределение данных MAP</h2>
      <div v-if="(mapTotal??0)>0" class="disk-bar" role="img" aria-label="Распределение физических блоков MAP по категориям">
        <span v-for="(g,i) in groupTotals" :key="g.label" class="seg" :style="{width:pct(g.value,mapTotal??0)+'%',background:groupColors[i]}"/>
      </div>
      <p v-else class="meta">{{mapTotal===null?'Ожидаем первый снимок реестра.':'Учтённых данных пока нет.'}}</p>
      <div v-for="(g,i) in groupTotals" :key="g.label" class="category-group">
        <details>
          <summary><span class="group-name"><i :style="{background:groupColors[i]}"/>{{g.label}}</span><strong>{{bytes(mapTotal===null||i===4&&!hostKnown&&!g.value?null:g.value)}}</strong></summary>
          <CategoryTable :categories="categories" :keys="g.keys" :unavailable="i===4?!hostKnown:!registry?.sampled_at"/>
        </details>
      </div>
      <CategoryTable v-if="remainder.length" :categories="categories" :keys="remainder"/>
      <details v-if="registry?.reference_history">
        <summary>Исторические образцы <strong>{{bytes(registry.reference_history.object_bytes+registry.reference_history.embedding_bytes)}}</strong></summary>
        <p class="meta">Подмножество общих образцов и эмбеддингов, не дополнительные байты. Используемые версии защищены.</p>
        <div class="row between wrap"><span>Объекты ({{registry.reference_history.objects}})</span><strong>{{bytes(registry.reference_history.object_bytes)}}</strong></div>
        <div class="row between wrap"><span>Эмбеддинги ({{registry.reference_history.embeddings}})</span><strong>{{bytes(registry.reference_history.embedding_bytes)}}</strong></div>
        <p v-if="registry.reference_history.partial" class="meta">Недоступно файлов: {{registry.reference_history.missing}}; выборка неполная.</p>
      </details>
      <p class="meta">Повторных hardlink-путей в реестре приложения: {{registry?.sampled_at?Object.values(registry.categories||{}).reduce((n,r)=>n+(r.hardlink_paths||0),0):'—'}}.</p>
      <p class="meta">На диске — выделенные блоки уникального inode. По файлам — сумма размеров всех путей, включая hardlink. История образцов, WAL и подкатегории не прибавляются к итогам повторно.</p>
    </section>
    <section class="panel stack">
      <h2>Docker и системные компоненты</h2>
      <p class="meta">Docker Engine показывает общие размеры образов, контейнеров, томов и BuildKit. Это не эксклюзивные физические байты MAP; значения не складываются с диаграммой.</p>
      <template v-if="host?.docker?.available">
        <div v-for="row in host.docker.shared_engine_totals" :key="row.Type" class="row between wrap"><span>{{row.Type}}</span><strong>{{row.Size||'—'}} <small class="meta">освобождаемо: {{row.Reclaimable||'—'}}</small></strong></div>
        <details><summary>Образы ревизий MAP</summary><div v-for="row in host.docker.map_revision_images" :key="row.ID+row.Tag" class="row between wrap"><code>{{row.Tag.slice(0,16)}}</code><span>{{row.Size}}</span></div></details>
        <p class="meta">Замер Docker: {{date(host.engine_sampled_at)}}</p>
      </template>
      <p v-else class="meta">Сведения Docker пока недоступны.</p>
      <details><summary>PostgreSQL, журналы и память</summary>
        <div class="row between wrap"><span>Размер БД (оценка PostgreSQL)</span><strong>{{bytes(usage.database_estimated_bytes)}}</strong></div>
        <div class="row between wrap"><span>WAL (часть PGDATA)</span><strong>{{bytes(host?.postgres_wal_subset_bytes)}}</strong></div>
        <p v-if="host?.postgres_wal_delta_bytes!=null" class="meta">Изменение WAL: {{host.postgres_wal_delta_bytes<0?'−':'+'}}{{bytes(Math.abs(host.postgres_wal_delta_bytes))}}</p>
        <p v-if="usage.postgres_diagnostics" class="meta">Долгих транзакций: {{usage.postgres_diagnostics.long_transactions}} · Autovacuum: {{usage.postgres_diagnostics.autovacuum_count}} · последнее: {{date(usage.postgres_diagnostics.last_autovacuum)}}</p>
        <div v-for="(row,name) in usage.journals?.services||{}" :key="name" class="row between wrap"><span>{{name}}</span><strong>{{bytes(row.bytes)}} / {{bytes(row.budget_bytes)}}{{row.partial?' (частично)':''}}</strong></div>
        <p class="meta">Tmpfs — память, не диск. Удалённые открытые файлы — нижняя оценка, отдельно от учтённых путей.</p>
        <div v-if="host?.tmpfs?.available" v-for="(row,key) in host.tmpfs.devices" :key="key" class="row between wrap"><span>tmpfs {{key}}</span><strong>{{bytes(row.used_bytes)}} / {{bytes(row.total_bytes)}}</strong></div>
        <div class="row between wrap"><span>Удалённые открытые файлы</span><strong>{{bytes(host?.deleted_open?.allocated_bytes)}}</strong></div>
      </details>
    </section>
  </div>
</template>
<style scoped>
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:12px}.metrics>div{display:grid;gap:6px;padding:12px;background:var(--panel-alt);border-radius:10px;min-width:0}.metrics strong{font-size:23px;overflow-wrap:anywhere}.smaller strong{font-size:18px}.disk{padding:8px 0}.disk-bar{height:18px;display:flex;overflow:hidden;border-radius:7px;background:var(--panel-alt);border:1px solid var(--border-subtle)}.seg{height:100%;flex:none}.map{background:#5679bc}.other{background:#84909f}.free{background:#43a18b}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.legend i,.group-name i{width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:6px;flex:none}.category-group{border-bottom:1px solid var(--border-subtle);padding:5px 0}summary{cursor:pointer;overflow-wrap:anywhere}summary strong{float:right;margin-left:6px}.group-name{display:inline}.category-group details[open] summary{margin-bottom:10px}.category-group summary{padding:5px 0}
@media(max-width:520px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.metrics strong{font-size:19px}.metrics>div{padding:9px}}
</style>
