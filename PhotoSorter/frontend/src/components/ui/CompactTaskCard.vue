<script setup lang="ts">
import {computed} from 'vue'
import UiIcon from './UiIcon.vue'

type Tone='running'|'queued'|'success'|'danger'|'warning'|'neutral'
const props=withDefaults(defineProps<{
  number:string|number
  title:string
  thumbnailUrl?:string|null
  icon?:'photos'|'references'|'results'
  status:string
  tone?:Tone
  progress?:number|null
  stage:string
  timeLabel?:string
  timeDetail?:string
  active?:boolean
}>(),{icon:'photos',tone:'neutral',progress:null,active:false})
const percentage=computed(()=>typeof props.progress==='number' &&
  Number.isFinite(props.progress) && props.progress>=0 && props.progress<=100
  ?Math.round(props.progress):null)
</script>
<template>
<article class="task-card" :class="{'task-card-active':active}">
  <div class="task-card-identity">
    <span class="task-card-number">{{number}}</span>
    <div class="task-card-thumbnail">
      <img v-if="thumbnailUrl" :src="thumbnailUrl" alt="" loading="lazy"/>
      <UiIcon v-else :name="icon" :size="22"/>
    </div>
    <div class="task-card-heading">
      <strong class="task-card-title" :title="title">{{title}}</strong>
      <div class="task-card-meta"><slot name="meta"/></div>
    </div>
  </div>
  <span class="task-card-status" :class="'task-card-status-'+tone">
    <span class="task-card-status-dot" aria-hidden="true"/>
    {{status}}
  </span>
  <div class="task-card-progress">
    <div class="task-card-progress-line">
      <div class="task-card-progress-track" :role="percentage!==null?'progressbar':undefined"
        :aria-valuenow="percentage??undefined" :aria-valuemin="percentage!==null?0:undefined"
        :aria-valuemax="percentage!==null?100:undefined"
        :aria-label="percentage!==null?'Общий прогресс '+title:undefined">
        <span v-if="percentage!==null" class="task-card-progress-fill"
          :style="{width:percentage+'%'}"/>
      </div>
      <strong class="task-card-percent">{{percentage===null?'—':percentage+'%'}}</strong>
    </div>
    <span class="task-card-stage" :title="stage">{{stage}}</span>
  </div>
  <div class="task-card-time">
    <strong>{{timeLabel||'—'}}</strong>
    <span v-if="timeDetail" :title="timeDetail">{{timeDetail}}</span>
  </div>
  <div class="task-card-actions">
    <slot name="actions"/>
    <details v-if="$slots.menu" class="task-card-menu">
      <summary title="Другие действия" aria-label="Другие действия">•••</summary>
      <div class="task-card-menu-content"><slot name="menu"/></div>
    </details>
  </div>
</article>
</template>
