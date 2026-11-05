<script setup lang="ts">
import {computed,nextTick,onMounted,onUnmounted,ref,watch} from 'vue'
import ThumbnailGrid from './ThumbnailGrid.vue'
import type {Tile} from './ThumbnailGrid.vue'

const props=withDefaults(defineProps<{items:Tile[];canDelete?:boolean;showScores?:boolean}>(),{canDelete:false,showScores:false})
const emit=defineEmits<{(e:'open',index:number):void;(e:'remove',id:string):void}>()
const host=ref<HTMLElement|null>(null)
const width=ref(780),top=ref(0),viewportY=ref(0),viewportHeight=ref(800),mobile=ref(false)
let resize:ResizeObserver|undefined
const gap=computed(()=>mobile.value?9:12)
const columns=computed(()=>mobile.value?2:Math.max(1,Math.floor((width.value+gap.value)/(154+gap.value))))
const rowHeight=computed(()=>{
  const colWidth=Math.max(80,(width.value-gap.value*(columns.value-1))/columns.value)
  return colWidth*.75+gap.value
})
const rows=computed(()=>Math.ceil(props.items.length/columns.value))
const startRow=computed(()=>Math.max(0,Math.floor((viewportY.value-top.value)/rowHeight.value)-4))
const endRow=computed(()=>Math.min(rows.value,Math.max(startRow.value+1,Math.ceil((viewportY.value+viewportHeight.value-top.value)/rowHeight.value)+5)))
const first=computed(()=>startRow.value*columns.value)
const visible=computed(()=>props.items.slice(first.value,endRow.value*columns.value))
const height=computed(()=>Math.max(0,rows.value*rowHeight.value-gap.value))
function measure(){
  if(!host.value)return
  const box=host.value.getBoundingClientRect()
  width.value=box.width||width.value
  top.value=box.top+window.scrollY
  mobile.value=window.innerWidth<=700
  viewportHeight.value=window.innerHeight
  viewportY.value=window.scrollY
}
onMounted(()=>{
  resize=new ResizeObserver(measure)
  if(host.value)resize.observe(host.value)
  window.addEventListener('scroll',measure,{passive:true})
  window.addEventListener('resize',measure,{passive:true})
  void nextTick(measure)
})
onUnmounted(()=>{resize?.disconnect();window.removeEventListener('scroll',measure);window.removeEventListener('resize',measure)})
watch(()=>props.items.length,()=>{void nextTick(measure)})
</script>
<template>
  <div ref="host" :style="{height:height+'px',position:'relative',width:'100%'}" :aria-label="'Галерея, '+items.length+' фотографий'">
    <div :style="{position:'absolute',top:startRow*rowHeight+'px',left:0,right:0}">
      <ThumbnailGrid :items="visible" :can-delete="canDelete" :show-scores="showScores"
        @open="index=>emit('open',first+index)" @remove="id=>emit('remove',id)"/>
    </div>
  </div>
</template>
