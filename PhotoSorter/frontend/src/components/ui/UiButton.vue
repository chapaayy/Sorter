<script setup lang="ts">
withDefaults(defineProps<{kind?:'primary'|'danger'|'ghost'|'secondary';loading?:boolean;disabled?:boolean;small?:boolean;type?:'button'|'submit'}>(),{kind:'secondary',type:'button'})
</script>
<template><button class="btn" :class="[kind,{small}]" :type="type" :disabled="disabled||loading" :aria-busy="loading||undefined"><span v-if="loading" class="btn-spinner" aria-hidden="true"></span><slot/></button></template>
