<script setup lang="ts">
defineProps<{name:'photos'|'references'|'processing'|'results'|'logs'|'settings'|'menu';size?:number}>()
</script>

<template>
  <svg :width="size||18" :height="size||18" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"
    focusable="false" aria-hidden="true">
    <template v-if="name==='photos'">
      <rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v5"/>
    </template>
    <template v-else-if="name==='references'">
      <rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="8" rx="1.5"/>
      <rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="13" width="8" height="8" rx="1.5"/>
    </template>
    <template v-else-if="name==='processing'">
      <circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/>
    </template>
    <template v-else-if="name==='results'">
      <rect x="4" y="3" width="16" height="18" rx="2"/><path d="m8 12 3 3 5-6"/>
    </template>
    <template v-else-if="name==='logs'">
      <rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M12 15h5"/>
    </template>
    <template v-else-if="name==='settings'">
      <path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.64 5.64l1.42 1.42m9.88 9.88 1.42 1.42M18.36 5.64l-1.42 1.42M7.06 16.94l-1.42 1.42"/>
      <circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>
    </template>
    <template v-else-if="name==='menu'">
      <path d="M4 7h16M4 12h16M4 17h16"/>
    </template>
  </svg>
</template>
