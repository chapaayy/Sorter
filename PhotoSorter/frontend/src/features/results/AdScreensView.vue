<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {adResultsApi} from '../../api/adResults'
import type {XfeatPhoto} from '../../api/adResults'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import ImageViewer from '../../components/gallery/ImageViewer.vue'

const props=defineProps<{runId:string}>()
const emit=defineEmits<{(e:'inspect',index:number):void}>()
const photos=ref<XfeatPhoto[]>([])
const cursor=ref<string|null>(null),started=ref(false),busy=ref(false),error=ref('')
const view=ref<number|null>(null)

async function more(){
  if(busy.value)return
  busy.value=true
  try{
    const result=await adResultsApi.screens(props.runId,started.value?cursor.value:null)
    photos.value.push(...result.photos)
    cursor.value=result.next_cursor
    started.value=true;error.value=''
  }catch(e){error.value=errorText(e)}
  finally{busy.value=false}
}
onMounted(()=>{void more()})
function status(value:string){
  return ({found:'Найден',not_found:'Не найден',no_annotations:'Нет разметки',
    unknown_construction:'Нет конструкции',error:'Ошибка',
    not_processed:'Нет результатов',queued:'В очереди',running:'Обработка'} as Record<string,string>)[value]||value
}
</script>
<template>
<section class="stack result-ad-view">
  <div class="row between wrap">
    <div><h2>По экранам · XFeat</h2><p class="meta">Сохранённая геометрия, источник разметки и оригинальные кадры. Нейросеть повторно не запускается.</p></div>
    <span class="meta">Загружено ФО: {{photos.length}}</span>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}} <UiButton small @click="more">Повторить</UiButton></div>
  <div v-for="photo in photos" :key="photo.index" class="panel result-screen-card">
    <div class="row between wrap">
      <strong>ФО №{{photo.index+1}} · {{photo.assigned_sam||'Без конструкции'}}</strong>
      <RouterLink v-if="photo.assigned_sam" class="meta"
        :to="{path:'/results/'+runId,query:{view:'sam',sam:photo.assigned_sam}}">К фотографиям конструкции</RouterLink>
      <span class="status" :class="photo.status==='found'?'ok':photo.status==='error'?'danger':''">{{status(photo.status)}}</span>
    </div>
    <div class="result-screen-body">
      <div class="result-screen-geometry">
        <img :src="photo.image_url" :alt="'Оригинал ФО №'+(photo.index+1)" loading="lazy"/>
        <svg v-if="photo.image_width&&photo.image_height" :viewBox="'0 0 '+photo.image_width+' '+photo.image_height"
          preserveAspectRatio="xMidYMid meet" aria-label="Сохранённые контуры обнаруженных экранов">
          <polygon v-for="screen in photo.screens.filter(item=>item.status==='found'&&item.corners?.length===4)"
            :key="screen.screen_id" :points="screen.corners?.map(point=>point.x+','+point.y).join(' ')"
            fill="rgba(52,211,153,.13)" stroke="#34d399"
            :stroke-width="Math.max(3,(photo.image_width||1000)*.003)"/>
        </svg>
      </div>
      <div class="stack-sm">
        <div v-if="!photo.screens.length" class="meta">{{photo.reason||'Данных о размеченных экранах нет.'}}</div>
        <div v-for="screen in photo.screens" :key="screen.screen_id" class="result-screen-row">
          <img v-if="screen.crop_url" :src="screen.crop_url" :alt="'Фрагмент '+(screen.screen_name||'экрана')" loading="lazy"/>
          <div class="stack-sm grow">
            <strong>{{screen.screen_name||'Экран'}} · {{status(screen.status)}}</strong>
            <span class="meta">{{screen.reason||'Нет описания'}}</span>
            <span class="meta">Образец: {{screen.reference_id||'—'}} · Разметка v{{screen.annotation_version??'—'}}</span>
            <span v-if="screen.matches!=null||screen.inliers!=null" class="meta">
              Совпадения {{screen.matches??'—'}} · Подтверждены {{screen.inliers??'—'}}
              · Ошибка {{screen.reprojection_error_px??'—'}} px
            </span>
          </div>
        </div>
        <UiButton small @click="emit('inspect',photo.index)">Геометрия и подробности XFeat</UiButton>
        <UiButton small @click="view=photos.findIndex(p=>p.index===photo.index)">Открыть оригинал</UiButton>
      </div>
    </div>
  </div>
  <EmptyState v-if="started&&!photos.length&&!busy" title="Результаты XFeat отсутствуют"
    detail="Проверьте состояние запуска. Старые сортировки могут не содержать обнаружения экранов."/>
  <div v-if="cursor||busy" class="row" style="justify-content:center">
    <UiButton :loading="busy" :disabled="busy" @click="more">Показать ещё ФО</UiButton>
  </div>
  <ImageViewer v-if="view!==null" :items="photos.map(p=>({src:p.image_url,label:'ФО №'+(p.index+1)}))"
    :initial="view" :allow-detection="true"
    @close="view=null" @detect="i=>{view=null;emit('inspect',photos[i].index)}"/>
</section>
</template>
