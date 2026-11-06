<script setup lang="ts">
import {computed,ref} from 'vue'
import type {Run} from '../../types/api'
import {date,runLabels} from '../../utils/format'
import {runDuration,runStat} from '../../utils/processingDashboard'
import RowCard from '../../components/ui/RowCard.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
const props=defineProps<{runs:Run[];names:Record<string,string>;total:number;loadingMore:boolean}>()
const emit=defineEmits<{(e:'more'):void}>()
const search=ref('')
const filtered=computed(()=>props.runs.filter(r=>
  (r.id+' '+(props.names[r.batch_id]||r.batch_id)).toLowerCase().includes(search.value.toLowerCase())))
</script>
<template>
<section class="stack" aria-label="История обработок">
  <div class="row between wrap">
    <h2 style="margin:0">История запусков</h2>
    <div class="row wrap">
      <span class="meta">Запусков: {{total}}</span>
      <input v-model="search" placeholder="Поиск запусков…" aria-label="Поиск запусков" style="max-width:280px"/>
    </div>
  </div>
  <div v-if="filtered.length" class="stack">
    <RowCard v-for="run in filtered" :key="run.id" icon="◉" :to="'/processing/'+run.id">
      <template #title>{{names[run.batch_id]||run.batch_id}}</template>
      <template #subtitle>{{date(run.actual_started_at||run.created_at||run.started_at)}} · MegaLoc · {{run.source==='automatic'?'автоматически':'вручную'}}</template>
      <template #status>
        {{runLabels[run.status]||run.status}}
        <span v-if="run.error"> · {{run.error}}</span>
      </template>
      <template #metrics>
        <div class="metric"><strong>{{runStat(run.models?.megaloc?.count)}}</strong><small>фото</small></div>
        <div class="metric"><strong>{{runStat(run.models?.megaloc?.groups)}}</strong><small>групп</small></div>
        <div class="metric"><strong>{{runDuration(run)}}</strong><small>длительность</small></div>
      </template>
    </RowCard>
  </div>
  <EmptyState v-else-if="!runs.length" title="История пуста" detail="Запускайте обработку из раздела «Фотоотчёты»." icon="◉"/>
  <div v-else class="meta">По запросу ничего не найдено среди загруженных запусков.</div>
  <div v-if="runs.length<total" class="pagination">
    <UiButton :loading="loadingMore" @click="emit('more')">Показать ещё</UiButton>
  </div>
</section>
</template>
