<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref} from 'vue'
import UiSelect from '../ui/UiSelect.vue'

export interface GroupItem{id:string;label:string;count:number}
const props=defineProps<{items:GroupItem[];modelValue:string;placeholder?:string}>()
const emit=defineEmits<{(e:'update:modelValue',value:string):void}>()

const search=ref('')
const filtered=computed(()=>props.items.filter(item=>item.label.toLowerCase().includes(search.value.toLowerCase())))
const aside=ref<HTMLElement|null>(null)
const width=ref(440)
const MIN_WIDTH=250
const MAX_WIDTH=720
const STORAGE_KEY='ps.group-picker.width'
let container:HTMLElement|null=null
let observer:ResizeObserver|null=null
let dragging:{pointerId:number;startX:number;startWidth:number}|null=null

function maximumWidth(){
  // Preserve useful space for the photo grid, especially at tablet widths.
  return Math.max(MIN_WIDTH,Math.min(MAX_WIDTH,(container?.clientWidth||960)-380))
}
function applyWidth(value:number){
  width.value=Math.max(MIN_WIDTH,Math.min(maximumWidth(),Math.round(value)))
  container?.style.setProperty('--split-panel-width',width.value+'px')
}
function persistWidth(){
  try{localStorage.setItem(STORAGE_KEY,String(width.value))}catch{/* Storage is optional. */}
}
function onPointerDown(event:PointerEvent){
  if(event.button!==0)return
  dragging={pointerId:event.pointerId,startX:event.clientX,startWidth:width.value}
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  event.preventDefault()
}
function onPointerMove(event:PointerEvent){
  if(!dragging||dragging.pointerId!==event.pointerId)return
  applyWidth(dragging.startWidth+event.clientX-dragging.startX)
}
function stopDragging(event:PointerEvent){
  if(!dragging||dragging.pointerId!==event.pointerId)return
  dragging=null
  persistWidth()
}
function onResizeKey(event:KeyboardEvent){
  if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
    event.preventDefault()
    applyWidth(width.value+(event.key==='ArrowRight'?40:-40))
    persistWidth()
  }else if(event.key==='Home'||event.key==='End'){
    event.preventDefault()
    applyWidth(event.key==='Home'?MIN_WIDTH:maximumWidth())
    persistWidth()
  }
}
onMounted(()=>{
  container=aside.value?.closest('.split') as HTMLElement|null
  let saved=440
  try{
    const raw=localStorage.getItem(STORAGE_KEY)
    if(raw!==null&&Number.isInteger(Number(raw)))saved=Number(raw)
  }catch{/* Storage is optional. */}
  applyWidth(saved)
  if(typeof ResizeObserver!=='undefined'&&container){
    observer=new ResizeObserver(()=>applyWidth(width.value))
    observer.observe(container)
  }
})
onUnmounted(()=>{
  observer?.disconnect()
  dragging=null
  container?.style.removeProperty('--split-panel-width')
})
</script>

<template>
  <div class="mobile-picker">
    <span class="label">Выбрать группу</span>
    <UiSelect label="Выбрать группу" :model-value="modelValue"
      :options="items.map(item=>({value:item.id,label:item.label+' · '+item.count}))"
      placeholder="Выберите группу" :disabled="!items.length"
      @update:model-value="emit('update:modelValue',$event)"/>
  </div>
  <aside ref="aside" class="panel split-aside">
    <input v-model="search" class="split-search" :placeholder="placeholder||'Найти…'"
      aria-label="Поиск групп"/>
    <nav class="split-list" aria-label="Выбор группы">
      <button v-for="item in filtered" :key="item.id" class="split-item"
        :class="{active:item.id===modelValue}"
        :aria-current="item.id===modelValue?'true':undefined"
        :aria-label="item.label+' · '+item.count"
        :title="item.label" @click="emit('update:modelValue',item.id)">
        <span class="split-item-label">{{item.label}}</span>
        <span class="split-item-count" aria-hidden="true">{{item.count}}</span>
      </button>
      <p v-if="!filtered.length" class="meta">Ничего не найдено</p>
    </nav>
    <button type="button" class="split-resize-handle"
      role="separator" aria-orientation="vertical"
      aria-label="Изменить ширину списка конструкций"
      :aria-valuenow="width" :aria-valuemin="MIN_WIDTH" :aria-valuemax="maximumWidth()"
      title="Потяните, чтобы показать адрес целиком. Стрелки ← → также меняют ширину."
      @pointerdown="onPointerDown" @pointermove="onPointerMove"
      @pointerup="stopDragging" @pointercancel="stopDragging"
      @keydown="onResizeKey">
      <span aria-hidden="true"></span>
    </button>
  </aside>
</template>
