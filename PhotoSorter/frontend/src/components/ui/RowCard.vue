<script setup lang="ts">
import {RouterLink} from 'vue-router'
defineProps<{icon?:string;to?:string}>()
</script>
<template>
  <component :is="to?RouterLink:'div'" :to="to||undefined" class="rowcard">
    <div class="rowcard-icon" aria-hidden="true">{{icon||'▤'}}</div>
    <div class="rowcard-content">
      <div class="rowcard-title"><slot name="title"/></div>
      <div class="rowcard-subtitle"><slot name="subtitle"/></div>
      <div class="rowcard-status"><slot name="status"/></div>
    </div>
    <div class="rowcard-metrics"><slot name="metrics"/></div>
    <div class="rowcard-arrow" aria-hidden="true">›</div>
  </component>
</template>
