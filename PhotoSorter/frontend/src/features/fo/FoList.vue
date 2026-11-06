<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {usePolling} from '../../composables/usePolling'
import type {Batch} from '../../types/api'
import {date,bytes,errorText} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import RowCard from '../../components/ui/RowCard.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import UploadPanel from './UploadPanel.vue'
import {useRouter} from 'vue-router'
const router=useRouter()
const batches=ref<Batch[]>([]),search=ref(''),showUpload=ref(false),loading=ref(true),error=ref('')
const offset=ref(0),total=ref(0)
const filtered=computed(()=>batches.value.filter(b=>b.delete_state!=='deleted'&&b.display_name.toLowerCase().includes(search.value.toLowerCase())))
async function load(more=false){
  loading.value=true;error.value=''
  try{
    const data=await batchApi.list(100,more?offset.value:0)
    batches.value=more?batches.value.concat(data.batches):data.batches
    offset.value=batches.value.length;total.value=data.total
  }catch(e){error.value=errorText(e)}finally{loading.value=false}
}
onMounted(()=>{void load()})
// Poll while deletion or interrupted transfers need attention.
usePolling(async()=>{
  if(batches.value.some(b=>b.delete_state==='deleting'||(b.pending??0)>0||b.upload_manifest_state==='waiting'||b.auto_process_state==='waiting'))await load()
},3000)
function status(b:Batch){
  if(b.delete_state!=='active')return 'Удаление: '+b.delete_state
  if(b.upload_manifest_state==='waiting')return '◌ Загрузка партии не завершена'
  if((b.pending??0)>0)return '◌ '+b.pending+' незавершённых загрузок'
  if(b.auto_process_state==='waiting')return '◌ Ожидает автоматической обработки'
  if(b.auto_process_run_id)return '✓ Автоматическое задание создано'
  if(b.thumbnail_state==='ready')return '✓ Миниатюры готовы'
  if(b.photos!=null&&b.photos>0)return '◌ Подготовка миниатюр'
  return '○ Ожидает фотографии'
}
</script>
<template>
<PageHeader eyebrow="БИБЛИОТЕКА ФО" title="Фотоотчёты" subtitle="Каждая папка — отдельная партия с собственной галереей и сроком хранения.">
  <template #actions><UiButton kind="primary" @click="showUpload=!showUpload">{{showUpload?'Скрыть загрузку':'+ Загрузить папку'}}</UiButton></template>
</PageHeader>
<UploadPanel v-if="showUpload" style="margin-bottom:24px" @finished="id=>{showUpload=false;void router.push('/fo/'+id)}"/>
<div class="toolbar"><input v-model="search" class="search" placeholder="Поиск по названию партии…" aria-label="Поиск фотоотчётов"/><span class="meta">Партий: {{total}}</span><UiButton small @click="load()">Обновить</UiButton></div>
<div v-if="error" class="alert error" role="alert">{{error}}</div>
<div v-if="filtered.length" class="stack">
  <RowCard v-for="b in filtered" :key="b.batch_id" icon="▤" :to="'/fo/'+b.batch_id">
    <template #title>{{b.display_name}}</template>
    <template #subtitle>{{date(b.created_at)}}</template>
    <template #status>{{status(b)}}</template>
    <template #metrics><div class="metric"><strong>{{b.photos??'—'}}</strong><small>фотографий</small></div><div class="metric"><strong>{{bytes(b.size_bytes)}}</strong><small>объём</small></div></template>
  </RowCard>
  <div v-if="offset<total" class="pagination"><UiButton :loading="loading" @click="load(true)">Показать ещё</UiButton></div>
</div>
<EmptyState v-else-if="!loading" title="Пока нет фотоотчётов" detail="Выберите папку, чтобы загрузить фотографии первой партии." icon="▤"><UiButton kind="primary" @click="showUpload=true">Загрузить папку</UiButton></EmptyState>
<div v-else class="meta">Загружаем список партий…</div>
</template>
