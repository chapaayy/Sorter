<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {referenceApi} from '../../api/references'
import type {ScreenAnnotation,ScreenDefinition,ScreenPoint,ScreenPhotoMetadata} from '../../api/references'
import type {Photo} from '../../types/api'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import UiSelect from '../../components/ui/UiSelect.vue'

const props=defineProps<{sam:string;photo:Photo}>()
const emit=defineEmits<{(e:'close'):void;(e:'saved'):void}>()
const meta=ref<ScreenPhotoMetadata|null>(null),screens=ref<ScreenDefinition[]>([])
const selected=ref('new'),name=ref('Экран 1'),busy=ref(false),error=ref('')
const imageError=ref(''),loaded=ref(false),svg=ref<SVGSVGElement|null>(null),dragging=ref<number|null>(null)
const corners=ref<ScreenPoint[]>([]),bandPercent=ref(2)
const selectedScreen=computed(()=>screens.value.find(s=>s.id===selected.value))
const annotation=computed<ScreenAnnotation|undefined>(()=>
  selectedScreen.value?.annotations.find(a=>a.reference_id===props.photo.id))
const options=computed(()=>[
  {value:'new',label:'+ Новый экран'},
  ...screens.value.map(s=>({value:s.id,label:s.name+' · '+s.annotations.length+' разм.'}))
])
const shortSide=computed(()=>Math.min(meta.value?.width||1,meta.value?.height||1))
const bandPx=computed(()=>Number((shortSide.value*bandPercent.value/100).toFixed(2)))
const polygon=computed(()=>corners.value.map(p=>p.x+','+p.y).join(' '))
const handleRadius=computed(()=>Math.max(7,shortSide.value*.012))
function defaultCorners(){
  const w=meta.value?.width||1,h=meta.value?.height||1
  return [{x:w*.2,y:h*.2},{x:w*.8,y:h*.2},{x:w*.8,y:h*.8},{x:w*.2,y:h*.8}]
}
function switchScreen(){
  const current=annotation.value
  corners.value=current?current.corners.map(p=>({...p})):defaultCorners()
  bandPercent.value=current?Number((current.band_width_px/shortSide.value*100).toFixed(1)):2
  error.value=''
}
watch(selected,switchScreen)
async function load(){
  busy.value=true
  try{
    const [metadata,saved]=await Promise.all([
      referenceApi.screenPhoto(props.sam,props.photo.id),referenceApi.screens(props.sam)
    ])
    meta.value=metadata;screens.value=saved.screens
    name.value='Экран '+(screens.value.length+1)
    switchScreen()
  }catch(e){error.value=errorText(e)}
  finally{busy.value=false}
}
function onImageLoad(event:Event){
  const image=event.target as HTMLImageElement
  const expected=(meta.value?.width||1)/(meta.value?.height||1)
  const actual=image.naturalWidth/image.naturalHeight
  // Safari/Chromium may decode a huge image at reduced resolution.
  // Matching aspect ratios preserve the source-pixel SVG mapping.
  if(!Number.isFinite(actual)||Math.abs(actual/expected-1)>.005){
    loaded.value=false
    imageError.value='Ориентация изображения в браузере не совпадает с исходной.'
  }else{loaded.value=true;imageError.value=''}
}
function start(index:number,event:PointerEvent){
  if(busy.value)return
  event.preventDefault()
  dragging.value=index
  svg.value?.setPointerCapture(event.pointerId)
}
function move(event:PointerEvent){
  if(dragging.value===null||!svg.value||!meta.value)return
  const matrix=svg.value.getScreenCTM()
  if(!matrix)return
  const point=svg.value.createSVGPoint()
  point.x=event.clientX;point.y=event.clientY
  const pos=point.matrixTransform(matrix.inverse())
  corners.value= corners.value.map((p,i)=>i===dragging.value?{
    x:Number(Math.max(0,Math.min(meta.value!.width,pos.x)).toFixed(2)),
    y:Number(Math.max(0,Math.min(meta.value!.height,pos.y)).toFixed(2))
  }:p)
}
function finish(event:PointerEvent){
  if(dragging.value!==null && svg.value?.hasPointerCapture(event.pointerId))
    svg.value.releasePointerCapture(event.pointerId)
  dragging.value=null
}
async function save(){
  if(!meta.value||!loaded.value||busy.value)return
  busy.value=true;error.value=''
  try{
    const geometry={corners:corners.value,band_width_px:bandPx.value}
    if(annotation.value)
      await referenceApi.updateAnnotation(props.sam,annotation.value.id,{...geometry,version:annotation.value.version})
    else
      await referenceApi.createAnnotation(props.sam,{
        ...geometry,reference_id:props.photo.id,
        screen_id:selected.value==='new'?null:selected.value,
        screen_name:selected.value==='new'?name.value.trim():null
      })
    emit('saved')
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function removeAnnotation(){
  const current=annotation.value
  if(!current||busy.value||!window.confirm('Удалить эту разметку? Другие ракурсы сохранятся.'))return
  busy.value=true
  try{await referenceApi.deleteAnnotation(props.sam,current.id);emit('saved')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function removeScreen(){
  if(!selectedScreen.value||busy.value||
     !window.confirm('Удалить экран и все его разметки на всех Образцах этой конструкции?'))return
  busy.value=true
  try{await referenceApi.deleteScreen(props.sam,selected.value);emit('saved')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
onMounted(()=>{void load()})
</script>

<template>
<Teleport to="body">
<div class="modal-overlay screen-editor-overlay" @click.self="emit('close')">
  <section class="modal screen-editor-modal" role="dialog" aria-modal="true" aria-label="Разметка экрана">
    <div class="row between wrap">
      <div><h2>Выделить экран</h2><div class="meta">{{sam}} · {{photo.name}}</div></div>
      <UiButton @click="emit('close')">Закрыть</UiButton>
    </div>
    <div v-if="error" class="alert error" role="alert">{{error}}</div>
    <div v-if="imageError" class="alert error" role="alert">{{imageError}}</div>
    <p v-if="!meta" class="meta">Получение исходных размеров и разметок…</p>
    <template v-else>
      <div class="screen-editor-controls">
        <label class="field">Экран конструкции
          <UiSelect v-model="selected" label="Экран конструкции" :options="options"/>
        </label>
        <label v-if="selected==='new'" class="field">Название экрана
          <input v-model="name" maxlength="80" placeholder="Экран 1"/>
        </label>
        <label class="field screen-editor-band">Толщина полосы поиска
          <input v-model.number="bandPercent" aria-label="Толщина полосы поиска" type="range"
            min="0.2" max="12" step="0.1"/>
          <span class="meta">{{bandPercent.toFixed(1)}}% меньшей стороны · {{bandPx.toFixed(1)}} px</span>
        </label>
      </div>
      <p class="meta">Перетаскивайте четыре угла по рамке экрана. Полупрозрачная полоса показывает
        область будущего поиска XFeat, не центр рекламного изображения.</p>
      <div class="screen-editor-stage">
        <img :src="photo.original_url||''" :alt="photo.name" @load="onImageLoad"
          @error="imageError='Не удалось загрузить исходный Образец';loaded=false"/>
        <svg v-if="loaded" ref="svg"
          :viewBox="'0 0 '+meta.width+' '+meta.height"
          preserveAspectRatio="xMidYMid meet" aria-label="Контур экрана"
          @pointermove="move" @pointerup="finish" @pointercancel="finish">
          <polygon :points="polygon" fill="rgba(16,185,129,.05)"
            stroke="rgba(16,185,129,.35)" :stroke-width="bandPx" stroke-linejoin="round"
            pointer-events="none"/>
          <polygon :points="polygon" fill="none" stroke="#34d399"
            :stroke-width="Math.max(2,shortSide*.002)" pointer-events="none"/>
          <circle v-for="(p,i) in corners" :key="i" :cx="p.x" :cy="p.y"
            :r="handleRadius" fill="#fff" stroke="#047857"
            :stroke-width="Math.max(2,shortSide*.002)"
            class="screen-editor-handle" :aria-label="'Угол '+(i+1)"
            @pointerdown.stop="start(i,$event)"/>
        </svg>
      </div>
      <div class="row between wrap meta">
        <span>Оригинал: {{meta.width}} × {{meta.height}} px</span>
        <span>Версия: {{annotation?.version||'новая'}}</span>
      </div>
      <div class="modal-actions wrap">
        <UiButton v-if="annotation" kind="danger" :disabled="busy" @click="removeAnnotation">Удалить разметку</UiButton>
        <UiButton v-if="selectedScreen" kind="danger" :disabled="busy" @click="removeScreen">Удалить экран</UiButton>
        <UiButton @click="emit('close')">Отмена</UiButton>
        <UiButton kind="primary" :loading="busy" :disabled="!loaded||(!name.trim()&&selected==='new')"
          @click="save">Сохранить разметку</UiButton>
      </div>
    </template>
  </section>
</div>
</Teleport>
</template>
