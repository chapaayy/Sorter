<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {adResultsApi} from '../../api/adResults'
import type {AdPhoto,AdvertisingLayout,TextSubgroup} from '../../api/adResults'
import {errorText} from '../../utils/format'
import GroupPicker from '../../components/split/GroupPicker.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import ImageViewer from '../../components/gallery/ImageViewer.vue'

const props=defineProps<{runId:string}>()
const emit=defineEmits<{(e:'inspect',index:number):void}>()
const layouts=ref<AdvertisingLayout[]>([]),layoutTotal=ref(0),selected=ref('')
const subgroups=ref<TextSubgroup[]>([]),subgroupTotal=ref(0),subgroup=ref('')
const photos=ref<AdPhoto[]>([]),photoTotal=ref(0),bestOnly=ref(false)
const loading=ref(true),photoBusy=ref(false),groupBusy=ref(false),error=ref('')
const state=ref('loading'),viewer=ref<number|null>(null)
let requestVersion=0
const layout=computed(()=>layouts.value.find(item=>item.id===selected.value))
const choices=computed(()=>layouts.value.map(item=>({
  id:item.id,label:item.name+(item.version!=null?' · v'+item.version:''),
  count:item.photos
})))
function photoUrl(index:number){return '/api/images/'+encodeURIComponent(props.runId)+'/megaloc/'+index+'?kind=query'}
async function moreLayouts(){
  try{
    loading.value=true
    const result=await adResultsApi.layouts(props.runId,50,layouts.value.length)
    layouts.value.push(...result.layouts)
    layoutTotal.value=result.total
    state.value=result.status
    if(!selected.value&&layouts.value.length)selected.value=layouts.value[0].id
    error.value=''
  }catch(e){error.value=errorText(e)}
  finally{loading.value=false}
}
async function fetchSubgroups(lid:string){
  groupBusy.value=true
  try{
    const res=await adResultsApi.textGroups(props.runId,{layout_id:lid,limit:100})
    if(selected.value===lid){
      subgroups.value=res.subgroups;subgroupTotal.value=res.total
    }
  }catch(e){if(selected.value===lid)error.value=errorText(e)}
  finally{if(selected.value===lid)groupBusy.value=false}
}
async function moreSubgroups(){
  if(!selected.value||groupBusy.value)return
  const lid=selected.value
  groupBusy.value=true
  try{
    const res=await adResultsApi.textGroups(props.runId,
      {layout_id:lid,limit:100,offset:subgroups.value.length})
    if(selected.value===lid){
      subgroups.value.push(...res.subgroups);subgroupTotal.value=res.total
    }
  }catch(e){error.value=errorText(e)}
  finally{groupBusy.value=false}
}
async function morePhotos(reset=false){
  if(!selected.value)return
  if(reset){
    requestVersion++;photos.value=[];photoTotal.value=0
  }else if(photoBusy.value)return
  const version=requestVersion
  const lid=selected.value,variant=subgroup.value,only=bestOnly.value
  photoBusy.value=true
  try{
    const result=await adResultsApi.photos(props.runId,lid,{
      subgroup_id:variant||undefined,best_only:only,limit:32,
      offset:photos.value.length
    })
    if(version===requestVersion&&selected.value===lid){
      photos.value.push(...result.photos);photoTotal.value=result.total;error.value=''
    }
  }catch(e){if(version===requestVersion)error.value=errorText(e)}
  finally{if(version===requestVersion)photoBusy.value=false}
}
watch(selected,async lid=>{
  requestVersion++;subgroup.value='';subgroups.value=[];subgroupTotal.value=0
  photos.value=[];photoTotal.value=0
  if(lid){void fetchSubgroups(lid);void morePhotos(true)}
})
watch([subgroup,bestOnly],()=>{void morePhotos(true)})
onMounted(()=>{void moreLayouts()})
function color(value:string){
  return value==='confirmed'?'ok':value==='unidentified'?'danger':''
}
</script>
<template>
<section class="stack result-ad-view">
  <div class="row between wrap">
    <div><h2>По рекламе</h2><p class="meta">Макеты из закреплённой библиотеки запуска, окончательные текстовые варианты и лучшие кадры.</p></div>
    <span class="meta">{{layoutTotal}} макетов / состояний</span>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <div v-if="layouts.length" class="split">
    <div class="stack">
      <GroupPicker v-model="selected" :items="choices" placeholder="Название макета / версия…"/>
      <UiButton v-if="layouts.length<layoutTotal" small :loading="loading" @click="moreLayouts">
        Ещё макеты · {{layouts.length}} / {{layoutTotal}}
      </UiButton>
    </div>
    <section class="panel split-main stack">
      <template v-if="layout">
        <div class="result-layout-header">
          <img v-if="layout.image_url" :src="layout.image_url" :alt="layout.name" loading="lazy"/>
          <div class="stack-sm grow">
            <h2>{{layout.name}} <span v-if="layout.version!=null" class="meta">v{{layout.version}}</span></h2>
            <div class="result-ad-metrics">
              <span>ФО: <strong>{{layout.photos}}</strong></span>
              <span>Текстовых групп: <strong>{{layout.subgroups}}</strong></span>
              <span>Подтверждено: <strong>{{layout.confirmed}}</strong></span>
              <span>Вероятно: <strong>{{layout.probable}}</strong></span>
            </div>
            <p v-if="layout.prepared_text" class="meta">Контрольный текст: {{layout.prepared_text}}</p>
            <p class="meta">Конструкции:
              <RouterLink v-for="(sam,i) in layout.constructions" :key="sam"
                :to="{path:'/results/'+runId,query:{view:'sam',sam}}">
                {{sam}}{{i<layout.constructions.length-1?', ':''}}
              </RouterLink>
              <span v-if="!layout.constructions.length">Не определены</span>
            </p>
          </div>
        </div>
        <div class="row between wrap">
          <strong>Текстовые варианты</strong>
          <label class="row result-ad-checkbox">
            <input v-model="bestOnly" type="checkbox"/>
            Только лучшие кадры
          </label>
        </div>
        <div class="row wrap result-ad-filters">
          <button class="result-ad-filter" :class="{active:!subgroup}" @click="subgroup=''">
            Все варианты
          </button>
          <button v-for="item in subgroups" :key="item.id"
            class="result-ad-filter" :class="{active:subgroup===item.id}" :title="item.reason"
            @click="subgroup=item.id">
            {{item.id}} · {{item.member_count}} · {{item.status}}
          </button>
          <UiButton v-if="subgroups.length<subgroupTotal" small :loading="groupBusy" @click="moreSubgroups">
            Ещё группы
          </UiButton>
        </div>
        <span class="meta">Найдено {{photoTotal}} кадров · загружено {{photos.length}}</span>
        <div class="result-ad-member-grid">
          <article v-for="(photo,i) in photos" :key="photo.index+':'+photo.screen_id+':'+photo.text_subgroup_id" class="result-ad-photo">
            <img :src="photo.crop_url" :alt="'Реклама с ФО '+(photo.index+1)" loading="lazy"/>
            <div class="stack-sm">
              <div class="row wrap">
                <strong>ФО №{{photo.index+1}}</strong>
                <span class="status" :class="color(photo.classification)">{{photo.classification}}</span>
                <span v-if="photo.best" class="status ok">Лучшее</span>
              </div>
              <span class="meta">{{photo.assigned_sam}} · {{photo.text_subgroup_id}} · {{photo.visual_group_id}}</span>
              <span class="meta">Качество: {{photo.quality?.status==='measured'?photo.quality.score.toFixed(2)+' / 100':'не измерено'}}</span>
              <span v-if="photo.quality?.metrics" class="meta">
                Фокус {{photo.quality.metrics.sharpness?.toFixed(3)??'—'}}
                · Блики {{photo.quality.metrics.glare?.toFixed(3)??'—'}}
                · Экспозиция {{photo.quality.metrics.exposure?.toFixed(3)??'—'}}
                · Видимость {{photo.quality.metrics.screen_coverage?.toFixed(3)??'—'}}
              </span>
              <span class="meta">OCR: {{photo.ocr_status||'не выполнено'}} · {{photo.ocr_reason||''}}</span>
              <div class="row wrap">
                <UiButton small @click="emit('inspect',photo.index)">ФО / XFeat</UiButton>
                <UiButton small @click="viewer=i">Оригинал</UiButton>
              </div>
            </div>
          </article>
        </div>
        <div v-if="photos.length<photoTotal" class="row" style="justify-content:center">
          <UiButton small :loading="photoBusy" @click="morePhotos()">Показать ещё</UiButton>
        </div>
        <EmptyState v-if="!photoBusy&&!photos.length" title="Для фильтра фотографий нет"
          detail="Проверьте другой макет, текстовую группу или отключите фильтр лучших кадров."/>
      </template>
    </section>
  </div>
  <EmptyState v-else-if="!loading" title="Распознанной рекламы нет"
    :detail="state==='not_processed'||state==='processing'?'Конвейер рекламы не выполнялся или ещё обрабатывается.':'В сохранённых результатах отсутствуют рекламные макеты и сопоставления.'"/>
  <ImageViewer v-if="viewer!==null" :items="photos.map(p=>({src:photoUrl(p.index),label:'ФО №'+(p.index+1)}))"
    :initial="viewer" :allow-detection="true" @close="viewer=null"
    @detect="i=>{viewer=null;emit('inspect',photos[i].index)}"/>
</section>
</template>
