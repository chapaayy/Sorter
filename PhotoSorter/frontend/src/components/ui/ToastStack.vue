<script setup lang="ts">
import {useNoticeStore} from '../../stores/notice'
const store=useNoticeStore()
</script>
<template>
  <div class="toast-stack" role="status" aria-live="polite">
    <div v-for="notice in store.notices" :key="notice.id" class="toast" :class="notice.kind">
      <span>{{notice.text}}</span>
      <button class="btn ghost small" :aria-label="'Закрыть: '+notice.text" @click="store.remove(notice.id)">×</button>
    </div>
  </div>
</template>
