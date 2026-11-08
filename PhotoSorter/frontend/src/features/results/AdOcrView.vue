<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {adResultsApi} from '../../api/adResults'
import type {OcrPhoto,OcrScreen} from '../../api/adResults'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import ImageViewer from '../../components/gallery/ImageViewer.vue'
import AdTextEvidence from './AdTextEvidence.vue'

const props=defineProps<{runId:string}>()
const emit=defineEmits<{(e:'inspect',index:number):void}>()
const route=useRoute(),router=useRouter()
const photos=ref<OcrPhoto[]>([]),cursor=ref<string|null>(null),started=ref(false)
const busy=ref(false),error=ref(''),expanded=ref<string[]>([]),viewer=ref<number|null>(null)
const key=(index:number,screen:OcrScreen)=>index+':'+screen.screen_id
function toggle(id:string){
  expanded.value=expanded.value.includes(id)?expanded.value.filter(value=>value!==id):[...expanded.value,id]
}
async function more(){
  if(busy.value)return
  busy.value=true
  try{
    const response=await adResultsApi.ocr(props.runId,started.value?cursor.value:null)
    photos.value.push(...response.photos)
    cursor.value=response.next_cursor;started.value=true;error.value=''
  }catch(e){error.value=errorText(e)}
  finally{busy.value=false}
}
onMounted(()=>{void more()})
function compare(group?:string){
  if(group)void router.push({path:route.path,query:{...route.query,view:'comparisons',group}})
}
</script>
<template>
<section class="stack result-ad-view">
  <div class="row between wrap">
    <div><h2>По рекламе (Текст) · PaddleOCR</h2>
      <p class="meta">Сохранённый распознанный текст каждого экрана, даты, числа, цены, противоречия и координаты текстовых областей.</p></div>
    <span class="meta">{{photos.length}} ФО · OCR не пересчитывается</span>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <section v-for="(photo,photoIndex) in photos" :key="photo.index" class="panel stack result-ocr-card">
    <div class="row between wrap">
      <strong>ФО №{{photo.index+1}} · {{photo.assigned_sam||'Конструкция не определена'}}</strong>
      <RouterLink v-if="photo.assigned_sam" class="meta"
        :to="{path:'/results/'+runId,query:{view:'sam',sam:photo.assigned_sam}}">К конструкции</RouterLink>
      <span class="status" :class="photo.status==='found'?'ok':''">XFeat: {{photo.status}}</span>
      <div class="row wrap">
        <UiButton small @click="viewer=photoIndex">Оригинал ФО</UiButton>
        <UiButton small @click="emit('inspect',photo.index)">Геометрия XFeat</UiButton>
      </div>
    </div>
    <div v-if="!photo.screens.length" class="meta">{{photo.reason||'Обнаруженных экранов нет'}}</div>
    <div v-for="screen in photo.screens" :key="screen.screen_id" class="result-ocr-item">
      <div class="row between wrap">
        <div class="stack-sm grow">
          <strong>{{screen.screen_name||'Экран'}} · {{screen.recognition?.layout_name||'Макет не определён'}}</strong>
          <span class="meta">ФО №{{photo.index+1}} · {{screen.recognition?.classification||screen.status}}</span>
          <span class="meta">{{screen.recognition?.ocr?.reason||screen.reason||'Диагностика ещё не опубликована'}}</span>
        </div>
        <UiButton small @click="toggle(key(photo.index,screen))">
          {{expanded.includes(key(photo.index,screen))?'Скрыть сравнение':'Текст и отличия'}}
        </UiButton>
      </div>
      <div class="result-ocr-item-body">
        <div v-if="screen.crop_url" class="result-ocr-image">
          <img :src="screen.crop_url" :alt="'Исходный фрагмент экрана №'+(photo.index+1)" loading="lazy"/>
          <svg v-if="screen.crop_box?.width&&screen.crop_box.height&&screen.recognition?.observation?.regions?.length"
            :viewBox="'0 0 '+screen.crop_box.width+' '+screen.crop_box.height"
            preserveAspectRatio="xMidYMid meet" aria-label="Сохранённые области OCR">
            <polygon v-for="(region,i) in screen.recognition.observation.regions" :key="i"
              :points="region.polygon?.map(point=>point.join(',')).join(' ')"
              fill="rgba(250,204,21,.12)" stroke="#facc15"
              :stroke-width="Math.max(1,screen.crop_box.width*.002)"/>
          </svg>
        </div>
        <div class="stack-sm grow">
          <span class="meta">Статус: <strong>{{screen.recognition?.ocr?.status||'нет результата'}}</strong>
            · Уверенность OCR: {{screen.recognition?.observation?.confidence?.toFixed(3)??'—'}}
          </span>
          <span class="meta">Прочитано: {{screen.recognition?.observation?.normalized_text||'—'}}</span>
          <span class="meta">Макет: {{screen.recognition?.layout_text||'Не идентифицирован'}}</span>
          <div class="row wrap">
            <span class="meta">Визуальная группа {{screen.recognition?.visual_group_id||'—'}}</span>
            <span class="meta">Текстовая группа {{screen.recognition?.text_subgroup_id||'—'}}</span>
            <UiButton v-if="screen.recognition?.visual_group_id" small
              @click="compare(screen.recognition.visual_group_id)">Сходство DINOv2</UiButton>
          </div>
        </div>
      </div>
      <AdTextEvidence v-if="expanded.includes(key(photo.index,screen))&&screen.recognition"
        :recognition="screen.recognition"/>
    </div>
  </section>
  <EmptyState v-if="started&&!photos.length&&!busy" title="OCR-результаты ещё не опубликованы"
    detail="Для этого запуска пока нет сохранённых результатов по экранам."/>
  <div v-if="cursor||busy" class="row" style="justify-content:center">
    <UiButton :loading="busy" @click="more">Показать ещё ФО</UiButton>
  </div>
  <ImageViewer v-if="viewer!==null" :items="photos.map(p=>({src:p.image_url,label:'ФО №'+(p.index+1)}))"
    :initial="viewer" :allow-detection="true" @close="viewer=null"
    @detect="i=>{viewer=null;emit('inspect',photos[i].index)}"/>
</section>
</template>
