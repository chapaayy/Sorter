<script setup lang="ts">
import {ref,computed,watch,onMounted,onUnmounted,nextTick} from 'vue'
import DeferredImage from './DeferredImage.vue'
export interface ViewerItem{src:string;label:string;score?:number|null;video?:boolean;poster?:string|null;fallbackMessage?:string;previewOnly?:boolean}
const props=defineProps<{items:ViewerItem[];initial:number}>()
const emit=defineEmits<{(e:'close'):void}>()
const index=ref(props.initial),zoom=ref(false),closeButton=ref<HTMLButtonElement|null>(null)
const failed=ref(false)
const current=computed(()=>props.items[index.value])
let touchX=0,focusBefore:HTMLElement|null=null
function move(dir:number){index.value=(index.value+dir+props.items.length)%props.items.length;zoom.value=false}
function key(e:KeyboardEvent){
  if(e.key==='Escape')emit('close')
  if(e.target instanceof HTMLVideoElement)return
  if(e.key==='ArrowLeft'){e.preventDefault();move(-1)}
  if(e.key==='ArrowRight'){e.preventDefault();move(1)}
}
function start(e:TouchEvent){touchX=e.changedTouches[0]?.clientX||0}
function end(e:TouchEvent){const delta=(e.changedTouches[0]?.clientX||0)-touchX;if(Math.abs(delta)>65&& !zoom.value)move(delta<0?1:-1)}
watch([index,()=>current.value?.src],()=>{failed.value=false})
watch(()=>props.initial,value=>{index.value=value;zoom.value=false})
onMounted(()=>{focusBefore=document.activeElement as HTMLElement;document.addEventListener('keydown',key);document.body.style.overflow='hidden';void nextTick(()=>closeButton.value?.focus())})
onUnmounted(()=>{document.removeEventListener('keydown',key);document.body.style.overflow='';focusBefore?.focus()})
</script>
<template>
<Teleport to="body"><div class="viewer-overlay">
  <section class="viewer" role="dialog" aria-modal="true" :aria-label="current?.video?'Просмотр видео':'Просмотр фотографии'">
    <div class="viewer-tools">
      <span class="meta">{{index+1}} / {{items.length}} · {{current?.label}} <span v-if="current?.score!=null">· score {{current.score.toFixed(3)}}</span></span>
      <div class="row">
        <button v-if="!current?.video" class="btn small" @click="zoom=!zoom">{{zoom?'Уменьшить':'Увеличить'}}</button>
        <button ref="closeButton" class="btn icon" aria-label="Закрыть просмотр" @click="emit('close')">×</button>
      </div>
    </div>
    <div class="viewer-main" @touchstart.passive="start" @touchend.passive="end" @dblclick="zoom=!zoom">
      <video v-if="current?.video&&current.src&&!failed" :key="current.src" :src="current.src" :poster="current.poster??undefined"
        controls playsinline preload="metadata" class="viewer-video" @error="failed=true"/>
      <DeferredImage v-else-if="current?.src&&!current.video" :key="current.src" :src="current.src" :alt="current.label" :class="{zoomed:zoom}">
        <template #error>
          <DeferredImage v-if="current.poster&&current.poster!==current.src" :key="current.poster" :src="current.poster" :alt="current.label"/>
          <p class="meta" v-if="!current.previewOnly" role="status">{{current.fallbackMessage||'Не удалось открыть фотографию'}}</p>
        </template>
      </DeferredImage>
      <div v-else class="viewer-fallback">
        <DeferredImage v-if="current?.poster" :key="current.poster" :src="current.poster" :alt="current.label"/>
        <p class="meta" role="status">{{current?.fallbackMessage||'Не удалось открыть файл'}}</p>
      </div>
    </div>
    <p v-if="current?.previewOnly" class="meta" role="status">{{current.fallbackMessage}}</p>
    <div class="row between" style="width:100%">
      <button class="btn" :disabled="items.length<2" aria-label="Предыдущее фото" @click="move(-1)">← Назад</button>
      <span class="meta">← → листать · двойное нажатие: масштаб</span>
      <button class="btn" :disabled="items.length<2" aria-label="Следующее фото" @click="move(1)">Вперёд →</button>
    </div>
  </section>
</div></Teleport>
</template>

<style scoped>
.viewer-fallback{text-align:center}
.viewer-video{display:block;max-width:100%;max-height:72vh;margin:auto;object-fit:contain}
</style>
