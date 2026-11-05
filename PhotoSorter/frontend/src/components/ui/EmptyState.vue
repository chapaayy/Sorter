<script setup lang="ts">
defineProps<{title:string;detail?:string;icon?:string}>()
</script>
<template><div class="empty"><div class="empty-icon" aria-hidden="true">{{icon||'▧'}}</div><strong>{{title}}</strong><p>{{detail}}</p><slot/></div></template>
