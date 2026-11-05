<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {runApi} from '../../api/runs'
import {batchApi} from '../../api/batches'
import type {Run,Batch} from '../../types/api'
import {date,isComplete,errorText,runLabels} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import RowCard from '../../components/ui/RowCard.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
const runs=ref<Run[]>([]),batches=ref<Batch[]>([]),loading=ref(true),error=ref(''),search=ref('')
const finished=computed(()=>runs.value.filter(r=>isComplete(r.status)&&name(r.batch_id).toLowerCase().includes(search.value.toLowerCase())))
function name(id:string){return batches.value.find(b=>b.batch_id===id)?.display_name||id}
async function load(){
  loading.value=true
  try{const [r,b]=await Promise.all([runApi.list(200),batchApi.list(200)]);runs.value=r.runs;batches.value=b.batches;error.value=''}
  catch(e){error.value=errorText(e)}finally{loading.value=false}
}
onMounted(()=>{void load()})
</script>
<template>
<PageHeader eyebrow="ГОТОВЫЕ ФОТОГРАФИИ" title="Результаты" subtitle="Сортировки по SAM и группам ФО. Полный архив доступен в каждом завершённом запуске."/>
<div class="toolbar"><input v-model="search" class="search" placeholder="Поиск по названию фотоотчёта…" aria-label="Поиск результатов"/><span class="meta">{{finished.length}} завершённых запусков</span><UiButton small @click="load">Обновить</UiButton></div>
<div v-if="error" class="alert error" role="alert">{{error}}</div>
<div v-if="finished.length" class="stack">
  <RowCard v-for="r in finished" :key="r.id" icon="▣" :to="'/results/'+r.id">
    <template #title>{{name(r.batch_id)}}</template>
    <template #subtitle>{{date(r.started_at)}} · MegaLoc</template>
    <template #status>{{runLabels[r.status]||r.status}} · сортировка готова к скачиванию</template>
    <template #metrics><div class="metric"><strong>{{r.models?.megaloc?.count??'—'}}</strong><small>фото</small></div><div class="metric"><strong>{{r.models?.megaloc?.groups??'—'}}</strong><small>групп</small></div></template>
  </RowCard>
</div>
<EmptyState v-else-if="!loading" title="Завершённых сортировок нет" detail="Запустите MegaLoc во вкладке «Обработка», затем результаты появятся здесь." icon="▣"><RouterLink class="btn primary" to="/processing">К обработке</RouterLink></EmptyState>
<div v-else class="meta">Загрузка результатов…</div>
</template>
