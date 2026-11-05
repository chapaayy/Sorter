<script setup lang="ts">
defineProps<{title:string;subtitle?:string;eyebrow?:string}>()
</script>
<template>
  <header class="page-head">
    <div><div v-if="eyebrow" class="eyebrow">{{eyebrow}}</div><h1>{{title}}</h1><p v-if="subtitle">{{subtitle}}</p></div>
    <div v-if="$slots.actions" class="row wrap"><slot name="actions"/></div>
  </header>
</template>
