<script setup lang="ts">
import {ref,computed,watch,onMounted,onUnmounted,nextTick} from 'vue'
export interface ViewerItem{src:string;label:string;score?:number|null}
const props=defineProps<{items:ViewerItem[];initial:number;allowAnnotate?:boolean;allowDetection?:boolean}>()
const emit=defineEmits<{(e:'close'):void;(e:'annotate',index:number):void;(e:'detect',index:number):void}>()
const index=ref(props.initial),zoom=ref(false),closeButton=ref<HTMLButtonElement|null>(null)
const current=computed(()=>props.items[index.value])
let touchX=0,focusBefore:HTMLElement|null=null
function move(dir:number){index.value=(index.value+dir+props.items.length)%props.items.length;zoom.value=false}
function key(e:KeyboardEvent){
  if(e.key==='Escape')emit('close')
  if(e.key==='ArrowLeft'){e.preventDefault();move(-1)}
  if(e.key==='ArrowRight'){e.preventDefault();move(1)}
}
function start(e:TouchEvent){touchX=e.changedTouches[0]?.clientX||0}
function end(e:TouchEvent){const delta=(e.changedTouches[0]?.clientX||0)-touchX;if(Math.abs(delta)>65&& !zoom.value)move(delta<0?1:-1)}
watch(()=>props.initial,value=>{index.value=value;zoom.value=false})
onMounted(()=>{focusBefore=document.activeElement as HTMLElement;document.addEventListener('keydown',key);document.body.style.overflow='hidden';void nextTick(()=>closeButton.value?.focus())})
onUnmounted(()=>{document.removeEventListener('keydown',key);document.body.style.overflow='';focusBefore?.focus()})
</script>
<template>
<Teleport to="body"><div class="viewer-overlay">
  <section class="viewer" role="dialog" aria-modal="true" aria-label="Просмотр фотографии">
    <div class="viewer-tools">
      <span class="meta">{{index+1}} / {{items.length}} · {{current?.label}} <span v-if="current?.score!=null">· score {{current.score.toFixed(3)}}</span></span>
      <div class="row">
        <button v-if="allowDetection" class="btn small" @click="emit('detect',index)">Диагностика XFeat</button>
        <button v-if="allowAnnotate" class="btn small" @click="emit('annotate',index)">Выделить экран</button>
        <button class="btn small" @click="zoom=!zoom">{{zoom?'Уменьшить':'Увеличить'}}</button>
        <button ref="closeButton" class="btn icon" aria-label="Закрыть просмотр" @click="emit('close')">×</button>
      </div>
    </div>
    <div class="viewer-main" @touchstart.passive="start" @touchend.passive="end" @dblclick="zoom=!zoom">
      <img v-if="current" :key="current.src" :src="current.src" :alt="current.label" :class="{zoomed:zoom}"/>
    </div>
    <div class="row between" style="width:100%">
      <button class="btn" :disabled="items.length<2" aria-label="Предыдущее фото" @click="move(-1)">← Назад</button>
      <span class="meta">← → листать · двойное нажатие: масштаб</span>
      <button class="btn" :disabled="items.length<2" aria-label="Следующее фото" @click="move(1)">Вперёд →</button>
    </div>
  </section>
</div></Teleport>
</template>
