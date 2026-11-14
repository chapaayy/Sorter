<script setup lang="ts">
import {bytes} from '../../utils/format'
defineProps<{completed:number;totalFiles:number;duplicates:number;sentBytes:number;totalBytes:number;percent:number}>()
</script>

<template>
  <div class="stack-sm">
    <div class="row between wrap meta">
      <span>Готово {{completed}} из {{totalFiles}}<template v-if="duplicates"> · дублей пропущено: {{duplicates}}</template></span>
      <span>{{bytes(sentBytes)}} / {{bytes(totalBytes)}}</span>
    </div>
    <div class="progress-track"><span class="progress-fill" :style="{width:percent+'%'}"/></div>
  </div>
</template>
