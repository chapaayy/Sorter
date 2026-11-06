<script setup lang="ts">
import {computed} from 'vue'
import type {Batch} from '../../types/api'
import {batchProcessing} from '../../utils/batchProcessing'
const props=withDefaults(defineProps<{batch:Batch;compact?:boolean}>(),{compact:false})
const state=computed(()=>batchProcessing(props.batch))
const showProgress=computed(()=>state.value.run?.status==='running')
const percent=computed(()=>state.value.overallPercent??state.value.stagePercent)
const progressKind=computed(()=>state.value.overallPercent!=null?'Общий прогресс':'Этап')
</script>
<template>
<div class="fo-processing" :class="{'fo-processing-compact':compact}">
  <div class="row between wrap">
    <span class="status" :class="state.tone==='ok'?'ok':state.tone==='danger'?'danger':''" data-testid="fo-processing-status">{{state.label}}</span>
    <span v-if="state.run" class="meta">MegaLoc · {{state.run.grouping_threshold?.toFixed(2)??'0.50'}}</span>
  </div>
  <p class="fo-processing-detail">{{state.detail}}</p>
  <template v-if="showProgress">
    <div class="row between fo-processing-progress-label">
      <span class="meta">{{progressKind}} · {{state.stageLabel}}</span>
      <strong>{{percent!=null?percent.toFixed(1)+'%':'—'}}</strong>
    </div>
    <div v-if="percent!=null" class="progress-track" role="progressbar"
      :aria-label="progressKind+' MegaLoc'" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100">
      <span class="progress-fill" :style="{width:percent+'%'}"/>
    </div>
    <div v-if="state.stageCounts" class="meta">{{state.stageCounts}}</div>
    <div v-if="state.overallPercent!=null&&state.stagePercent!=null" class="meta">Прогресс текущего этапа: {{state.stagePercent.toFixed(1)}}%</div>
  </template>
</div>
</template>
