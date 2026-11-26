<script setup lang="ts">
import {computed} from 'vue'
import {bytes,date} from '../../../utils/format'
import type {StorageUsage} from '../../../types/api'
const props=defineProps<{usage:StorageUsage}>()
const registry=computed(()=>props.usage.registry)
const host=computed(()=>props.usage.host)
const logical=computed(()=>registry.value?.logical_bytes==null||!host.value?.at?null:registry.value.logical_bytes+Object.values(host.value.categories||{}).reduce((n,r)=>n+r.logical_bytes,0))
const physical=computed(()=>registry.value?.allocated_bytes==null||!host.value?.at?null:registry.value.allocated_bytes+Object.values(host.value.categories||{}).reduce((n,r)=>n+r.allocated_bytes,0))
const saved=computed(()=>logical.value==null||physical.value==null?null:logical.value-physical.value)
</script>
<template>
<div class="stack">
  <section class="panel stack">
    <h2>Физический и логический учёт файлов</h2>
    <div class="row between wrap"><span>Физические блоки файлов</span><strong>{{bytes(physical)}}</strong></div>
    <div class="row between wrap"><span>Логический размер</span><strong>{{bytes(logical)}}</strong></div>
    <div class="row between wrap"><span>Разница логического и физического размера (включая hardlink)</span><strong>{{saved==null?'—':(saved<0?'−':'')+bytes(Math.abs(saved))}}</strong></div>
    <p class="meta">Снимок реестра: {{date(registry?.sampled_at)}} · снимок хоста: {{date(host?.at)}}. Разница включает разреженные файлы и округление блоков, а не только hardlink.</p>
    <div v-for="(fs,key) in usage.filesystems||{}" :key="key" class="row between wrap"><span>Файловая система {{key}} · занято {{bytes(fs.used_bytes)}} / {{bytes(fs.total_bytes)}}</span><strong>Учтённые файлы MAP: {{bytes(fs.map_allocated_bytes)}}</strong></div>
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
        <p class="meta">Бюджеты журналов — во вкладке «Лимиты и хранение».</p>
        <p class="meta">Tmpfs — память, не диск. Удалённые открытые файлы — нижняя оценка, отдельно от учтённых путей.</p>
        <div v-if="host?.tmpfs?.available" v-for="(row,key) in host.tmpfs.devices" :key="key" class="row between wrap"><span>tmpfs {{key}}</span><strong>{{bytes(row.used_bytes)}} / {{bytes(row.total_bytes)}}</strong></div>
        <div class="row between wrap"><span>Удалённые открытые файлы</span><strong>{{bytes(host?.deleted_open?.allocated_bytes)}}</strong></div>
      </details>
    </section>
  </div>

</template>
<style scoped>summary{cursor:pointer;overflow-wrap:anywhere}summary strong{float:right;margin-left:6px}</style>
