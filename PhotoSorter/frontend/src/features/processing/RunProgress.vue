<script setup lang="ts">
import {computed} from 'vue'
import type {Run} from '../../types/api'
import {duration,runLabels,isActive} from '../../utils/format'
const props=defineProps<{run:Run}>()
const p=computed(()=>props.run.progress||{})
const stage=computed(()=>p.value.stage_label||p.value.stage||'Ожидание начала')
const percent=computed(()=>p.value.stage_percent!=null?Math.max(0,Math.min(100,p.value.stage_percent)):null)
const eta=computed(()=>p.value.eta_status==='measured'&&p.value.estimated_remaining_seconds!=null?duration(p.value.estimated_remaining_seconds):null)
</script>
<template>
<section class="panel stack" aria-live="polite">
  <div class="panel-header">
    <div><span class="eyebrow">ТЕКУЩИЙ ЗАПУСК · MEGALOC</span><h2 style="margin:8px 0 0">{{runLabels[run.status]||run.status}}</h2></div>
    <span v-if="run.status==='queued'" class="status">Очередь №{{run.queue_position||'—'}}</span>
    <span v-else class="status" :class="run.status==='completed'?'ok':run.status==='failed'?'danger':''">{{run.status}}</span>
  </div>
  <div v-if="run.status==='queued'" class="alert">Задание поставлено в очередь. MegaLoc начинает только после завершения предыдущего запуска.</div>
  <template v-else-if="isActive(run.status)">
    <div class="row between wrap"><div><strong>{{stage}}</strong><div v-if="p.detail" class="meta" style="margin-top:4px">{{p.detail.split(/[\\/]/).pop()}}</div></div><strong>{{percent!=null?percent.toFixed(1)+'%':'—'}}</strong></div>
    <div v-if="percent!=null" class="progress-track" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100"><span class="progress-fill" :style="{width:percent+'%'}"/></div>
    <div v-else class="meta">Пока нет измерений прогресса этого этапа.</div>
    <div class="row wrap kpis">
      <div><strong>{{p.total!=null?p.current||0:'—'}} / {{p.total??'—'}}</strong>Сделано / всего на этапе</div>
      <div><strong>{{p.stage_items_per_second!=null?p.stage_items_per_second.toFixed(2):'—'}}</strong>Ед./сек, измерено</div>
      <div><strong>{{duration(p.elapsed_seconds)}}</strong>Время выполнения</div>
      <div><strong>{{eta||'—'}}</strong>{{eta?'Прогноз до конца':'ETA пока нет'}}</div>
    </div>
    <div v-if="p.overall_percent!=null" class="meta">Общая оценка: {{p.overall_percent.toFixed(1)}}% · {{p.eta_status==='measured'?'на основании реальных измерений':'предварительно'}}</div>
  </template>
  <div v-else class="meta">{{run.error||'Просмотреть результаты или журнал можно из карточки запуска.'}}</div>
</section>
</template>
