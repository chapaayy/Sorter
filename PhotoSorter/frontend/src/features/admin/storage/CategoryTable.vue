<script setup lang="ts">
import {computed} from 'vue'
import {bytes} from '../../../utils/format'
import {categoryName} from './labels'
import type {StorageCounter} from '../../../types/api'
const props=defineProps<{categories:Record<string,StorageCounter|undefined>;keys?:string[];unavailable?:boolean}>()
const rows=computed(()=>(props.keys||Object.keys(props.categories)).map(key=>({key,value:props.categories[key]})))
</script>
<template>
  <div class="category-table">
    <div class="category-row table-head"><span>Категория</span><span>На диске</span><span>По файлам</span></div>
    <div v-for="row in rows" :key="row.key" class="category-row">
      <span>{{categoryName(row.key)}} <small v-if="row.value?.files" class="meta">({{row.value.files.toLocaleString('ru-RU')}})</small></span>
      <strong>{{bytes(row.value?.allocated_bytes??(unavailable?null:0))}}</strong>
      <span class="meta">{{bytes(row.value?.logical_bytes??(unavailable?null:0))}}</span>
    </div>
    <p v-if="!rows.length" class="meta">Нет учтённых файлов.</p>
  </div>
</template>
<style scoped>
.category-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(64px,110px) minmax(64px,110px);gap:10px;padding:9px 0;border-bottom:1px solid var(--border-subtle);align-items:center}
.category-row>:first-child{overflow-wrap:anywhere}.category-row>:nth-child(n+2){text-align:right;white-space:nowrap}.table-head{font-size:12px;color:var(--muted)}
@media(max-width:520px){.category-row{grid-template-columns:minmax(0,1fr) 72px 72px;gap:5px;font-size:12px}}
</style>
