<script setup lang="ts">
import {ref,computed,watch,onMounted,onUnmounted,nextTick} from 'vue'
import DeferredImage from './DeferredImage.vue'

export interface ViewerItem{
  src:string;label:string;score?:number|null;video?:boolean;poster?:string|null
  fallbackMessage?:string;previewOnly?:boolean
}
const props=defineProps<{items:ViewerItem[];initial:number}>()
const emit=defineEmits<{(e:'close'):void}>()
const index=ref(props.initial)
const current=computed(()=>props.items[index.value])
const failed=ref(false),closeButton=ref<HTMLButtonElement|null>(null)
const videoNode=ref<HTMLVideoElement|null>(null)
const stage=ref<HTMLElement|null>(null)
const scale=ref(1),offsetX=ref(0),offsetY=ref(0),dragging=ref(false)
const style=computed(()=>({
  transform:`translate(${offsetX.value}px,${offsetY.value}px) scale(${scale.value})`,
  transition:dragging.value?'none':'transform .12s ease-out'
}))
const pointers=new Map<number,{x:number;y:number}>()
let pinchDistance=0,pinchScale=1,touchX=0,focusBefore:HTMLElement|null=null,priorOverflow=''

function clamp(value:number,min:number,max:number){return Math.min(max,Math.max(min,value))}
function clampPan(){
  if(scale.value===1){offsetX.value=0;offsetY.value=0;return}
  const w=stage.value?.clientWidth||800,h=stage.value?.clientHeight||600
  offsetX.value=clamp(offsetX.value,-w*(scale.value-1)/2,w*(scale.value-1)/2)
  offsetY.value=clamp(offsetY.value,-h*(scale.value-1)/2,h*(scale.value-1)/2)
}
function setZoom(value:number){
  scale.value=clamp(Math.round(value*100)/100,1,8)
  clampPan()
}
function resetImage(){
  scale.value=1;offsetX.value=0;offsetY.value=0
  pointers.clear();dragging.value=false;pinchDistance=0;failed.value=false
}
function move(direction:number){
  if(props.items.length<2)return
  index.value=(index.value+direction+props.items.length)%props.items.length
  resetImage()
}
function key(event:KeyboardEvent){
  if(event.key==='Escape'){emit('close');return}
  if(event.target instanceof HTMLVideoElement)return
  if(event.key==='ArrowLeft'){event.preventDefault();move(-1)}
  if(event.key==='ArrowRight'){event.preventDefault();move(1)}
}
function wheel(event:WheelEvent){if(!current.value?.video)setZoom(scale.value+(event.deltaY<0?.4:-.4))}
function toggleZoom(){if(!current.value?.video)setZoom(scale.value>1?1:2.5)}
function pointDistance(){
  const [a,b]=[...pointers.values()]
  return a&&b?Math.hypot(a.x-b.x,a.y-b.y):0
}
function pointerDown(event:PointerEvent){
  if(current.value?.video)return
  pointers.set(event.pointerId,{x:event.clientX,y:event.clientY})
  if(pointers.size===2){pinchDistance=pointDistance();pinchScale=scale.value}
  if(scale.value>1||event.pointerType==='touch'){
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  }
}
function pointerMove(event:PointerEvent){
  const prev=pointers.get(event.pointerId)
  if(!prev)return
  pointers.set(event.pointerId,{x:event.clientX,y:event.clientY})
  if(pointers.size>=2&&pinchDistance>0){
    setZoom(pinchScale*pointDistance()/pinchDistance)
  }else if(scale.value>1){
    dragging.value=true
    offsetX.value+=event.clientX-prev.x
    offsetY.value+=event.clientY-prev.y
    clampPan()
  }
}
function pointerUp(event:PointerEvent){
  pointers.delete(event.pointerId)
  if(pointers.size<2)pinchDistance=0
  if(!pointers.size)dragging.value=false
}
function touchStart(event:TouchEvent){touchX=event.changedTouches[0]?.clientX||0}
function touchEnd(event:TouchEvent){
  const delta=(event.changedTouches[0]?.clientX||0)-touchX
  if(scale.value===1&&Math.abs(delta)>65)move(delta<0?1:-1)
}
function fullscreenVideo(){
  if(videoNode.value?.requestFullscreen)void videoNode.value.requestFullscreen()
}
watch(index,resetImage)
watch(()=>current.value?.src,resetImage)
watch(()=>props.initial,value=>{index.value=value;resetImage()})
onMounted(()=>{
  focusBefore=document.activeElement as HTMLElement
  priorOverflow=document.body.style.overflow
  document.addEventListener('keydown',key)
  document.body.style.overflow='hidden'
  void nextTick(()=>closeButton.value?.focus())
})
onUnmounted(()=>{
  document.removeEventListener('keydown',key)
  document.body.style.overflow=priorOverflow
  focusBefore?.focus()
})
</script>
<template>
<Teleport to="body">
  <div class="viewer-overlay">
    <section class="viewer" role="dialog" aria-modal="true"
      :aria-label="current?.video?'Просмотр видео':'Просмотр фотографии'">
      <div class="viewer-tools">
        <span class="viewer-filename">
          {{index+1}} / {{items.length}} · {{current?.label}}
          <span v-if="current?.score!=null"> · score {{current.score.toFixed(3)}}</span>
        </span>
        <div class="row viewer-controls">
          <template v-if="!current?.video">
            <button class="btn small" aria-label="Уменьшить" :disabled="scale<=1"
              @click="setZoom(scale-.5)">−</button>
            <span class="meta">{{Math.round(scale*100)}}%</span>
            <button class="btn small" aria-label="Увеличить" :disabled="scale>=8"
              @click="setZoom(scale+.5)">+</button>
            <button class="btn small" aria-label="Вписать фотографию" @click="setZoom(1)">Вписать</button>
          </template>
          <button v-if="current?.video&&!failed" class="btn small" @click="fullscreenVideo">На весь экран</button>
          <button ref="closeButton" class="btn icon" aria-label="Закрыть просмотр"
            @click="emit('close')">×</button>
        </div>
      </div>
      <div class="viewer-main">
        <video v-if="current?.video&&current.src&&!failed" ref="videoNode" :key="current.src"
          :src="current.src" :poster="current.poster??undefined"
          controls playsinline preload="metadata" class="viewer-video" @error="failed=true"/>
        <div v-else-if="current?.src&&!current.video" ref="stage" class="viewer-image-stage"
          :class="{'viewer-image-zoomed':scale>1}" @wheel.prevent="wheel"
          @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp"
          @pointercancel="pointerUp" @touchstart.passive="touchStart" @touchend.passive="touchEnd"
          @dblclick="toggleZoom">
          <DeferredImage :key="current.src" :src="current.src" :alt="current.label"
            draggable="false" :style="style" :class="{'viewer-draggable':scale>1}">
            <template #error>
              <DeferredImage v-if="current.poster&&current.poster!==current.src"
                :src="current.poster" :alt="current.label"/>
              <p v-if="!current.previewOnly" class="meta" role="status">
                {{current.fallbackMessage||'Не удалось открыть фотографию'}}
              </p>
            </template>
          </DeferredImage>
        </div>
        <div v-else class="viewer-fallback">
          <DeferredImage v-if="current?.poster" :src="current.poster" :alt="current.label"/>
          <p class="meta" role="status">{{current?.fallbackMessage||'Не удалось открыть файл'}}</p>
        </div>
      </div>
      <p v-if="current?.previewOnly" class="meta" role="status">{{current.fallbackMessage}}</p>
      <div class="row between viewer-footer">
        <button class="btn" :disabled="items.length<2" aria-label="Предыдущее фото"
          @click="move(-1)">← Назад</button>
        <span class="meta">← → листать · колёсико: масштаб · перетаскивание: перемещение</span>
        <button class="btn" :disabled="items.length<2" aria-label="Следующее фото"
          @click="move(1)">Вперёд →</button>
      </div>
    </section>
  </div>
</Teleport>
</template>
<style scoped>
.viewer-filename{font-size:12px;color:var(--muted);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.viewer-controls{flex:none;gap:6px}
.viewer-main{position:relative}
.viewer-image-stage{width:100%;height:100%;display:flex;align-items:center;
  justify-content:center;overflow:hidden;touch-action:pan-y;user-select:none}
.viewer-image-stage.viewer-image-zoomed{cursor:grab;touch-action:none}
.viewer-image-stage :deep(img){display:block;max-width:100%;max-height:100%;
  object-fit:contain;user-select:none}
.viewer-draggable{cursor:grab}
.viewer-video{display:block;max-width:100%;max-height:100%;margin:auto;object-fit:contain}
.viewer-fallback{text-align:center}
.viewer-footer{width:100%;flex:none}
@media(max-width:700px){
  .viewer-controls{flex-wrap:wrap;justify-content:flex-end}
  .viewer-footer .meta{display:none}
}
</style>
