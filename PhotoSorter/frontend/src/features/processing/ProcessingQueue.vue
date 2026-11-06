<script setup lang="ts">
import type {Run} from '../../types/api'
import {date} from '../../utils/format'
import {canRequestStop} from '../../utils/processingDashboard'
import UiButton from '../../components/ui/UiButton.vue'

defineProps<{
  runs:Run[]
  names:Record<string,string>
  busyId:string
  total:number
}>()
const emit=defineEmits<{(e:'stop',run:Run):void}>()
</script>
<template>
<section class="panel stack" aria-label="Очередь обработок">
  <div class="row between wrap">
    <h2 style="margin:0">Очередь обработок</h2>
    <span class="meta">{{total}} ожидают</span>
  </div>
  <div v-if="!runs.length" class="meta">Очередь пуста. Запуск следующей партии доступен в разделе «ФО».</div>
  <div v-for="run in runs" :key="run.id" class="processing-queue-row">
    <span class="processing-queue-position">{{run.queue_position??'—'}}</span>
    <div class="processing-queue-text">
      <RouterLink :to="'/processing/'+run.id" class="processing-queue-name">
        {{names[run.batch_id]||run.batch_id}}
      </RouterLink>
      <span class="meta">MegaLoc · порог {{run.grouping_threshold?.toFixed(2)??'0.50'}}
        · {{date(run.created_at||run.started_at)}} · {{run.source==='automatic'?'автоматически':'вручную'}}</span>
    </div>
    <div class="row wrap">
      <RouterLink :to="'/fo/'+run.batch_id" class="btn small">ФО</RouterLink>
      <UiButton v-if="canRequestStop(run)" small :loading="busyId===run.id" @click="emit('stop',run)">Убрать из очереди</UiButton>
    </div>
  </div>
</section>
