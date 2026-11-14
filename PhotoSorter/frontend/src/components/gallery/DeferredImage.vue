<script setup lang="ts">
import {onMounted,onUpdated,ref} from 'vue'

defineOptions({inheritAttrs:false})
defineProps<{src:string;alt:string;lazy?:boolean}>()
const state=ref<'loading'|'ready'|'failed'>('loading')
const img=ref<HTMLImageElement|null>(null)
function sync(){
  const node=img.value
  if(node?.complete)state.value=node.naturalWidth?'ready':'failed'
}
onMounted(sync)
onUpdated(sync)
</script>

<template>
  <img ref="img" v-bind="$attrs" :src="src" :alt="alt" :loading="lazy?'lazy':undefined" decoding="async"
    :class="{'deferred-image-pending':state!=='ready'}"
    @load="state='ready'" @error="state='failed'"/>
  <span v-if="state==='loading'" class="deferred-image-fill skeleton-shape" aria-hidden="true"/>
  <slot v-else-if="state==='failed'" name="error"/>
</template>
