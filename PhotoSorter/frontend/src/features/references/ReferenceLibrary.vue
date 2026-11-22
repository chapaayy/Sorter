<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,ref,watch} from 'vue'
import {referenceApi,type UpdatedConstruction} from '../../api/references'
import {regionApi,type Region} from '../../api/regions'
import RegionPicker from '../../components/regions/RegionPicker.vue'
import {useCursor} from '../../composables/useCursor'
import {usePolling} from '../../composables/usePolling'
import {useNoticeStore} from '../../stores/notice'
import type {Photo,SamCount} from '../../types/api'
import {errorText} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
import GroupPicker from '../../components/split/GroupPicker.vue'
import VirtualThumbnailGrid from '../../components/gallery/VirtualThumbnailGrid.vue'
import ImageViewer from '../../components/gallery/ImageViewer.vue'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import EditConstructionDialog from './EditConstructionDialog.vue'
import AssignSideDialog from './AssignSideDialog.vue'
const list=ref<SamCount[]>([]),regionChosen=ref('*'),regionRows=ref<Region[]>([])
const selected=ref(''),editing=ref(false),
  error=ref(''),busy=ref(false),viewer=ref<number|null>(null),
  deletePhoto=ref<string|null>(null),deleteSam=ref(false)

const notice=useNoticeStore(),uploader=useUploadCenterStore()
const galleryScroll=ref<HTMLElement|null>(null)
const chosen=ref<string[]>([])
const selectionMode=ref(false),selectingAll=ref(false),sideDialog=ref(false)
const chosenSet=computed(()=>new Set(chosen.value))
const viewerItems=ref<Photo[]>([])
const awaitingDeletion=ref(false)
const listLoading=ref(true)
const filteredConstructions=computed(()=>list.value.filter(s=>
  regionChosen.value==='*'||(regionChosen.value==='?'&&!s.city_code)||
  s.city_code===regionChosen.value))
const groups=computed(()=>filteredConstructions.value.map(s=>
  ({id:s.sam,label:s.display_name||s.sam,count:s.photos})))
watch(groups,()=>{
  if(!groups.value.some(x=>x.id===selected.value))selected.value=groups.value[0]?.id||''
})
const selectedEntry=computed(()=>list.value.find(item=>item.sam===selected.value))
const {items,cursor,loading,error:galleryError,load,reset}=useCursor<Photo>(cursor=>referenceApi.gallery(selected.value,cursor))
const preview=computed(()=>viewerItems.value.map(p=>({
  src:p.play_url||p.preview_url||p.original_url||'',label:p.name,
  video:p.media_kind==='video',poster:p.thumbnail_url
})))
const sideGroups=computed(()=>{
  const bySide=new Map<string,Photo[]>()
  for(const photo of items.value){
    const key=photo.side||''
    if(!bySide.has(key))bySide.set(key,[])
    bySide.get(key)!.push(photo)
  }
  return [...bySide].sort(([a],[b])=>!a?-1:!b?1:a.localeCompare(b,'ru',{numeric:true}))
    .map(([side,photos])=>({side,photos}))
})
function openGroup(photos:Photo[],index:number){viewerItems.value=photos;viewer.value=index}
function togglePhoto(id:string){
  chosen.value=chosen.value.includes(id)?chosen.value.filter(x=>x!==id):[...chosen.value,id]
}
function toggleSelectionMode(){
  if(busy.value||selectingAll.value)return
  selectionMode.value=!selectionMode.value
  chosen.value=[]
  sideDialog.value=false
}
async function selectAll(){
  if(!selectionMode.value||selectingAll.value||busy.value||loading.value)return
  const sam=selected.value
  selectingAll.value=true
  loading.value=true
  try{
    const all=new Map(items.value.map(photo=>[photo.id,photo]))
    let next=cursor.value
    const visited=new Set<string>()
    while(next){
      if(visited.has(next))throw new Error('Ошибка загрузки списка образцов')
      visited.add(next)
      const page=await referenceApi.gallery(sam,next)
      if(selected.value!==sam||!selectionMode.value)return
      for(const photo of page.photos)all.set(photo.id,photo)
      next=page.next_cursor
    }
    if(selected.value!==sam||!selectionMode.value)return
    items.value=[...all.values()]
    cursor.value=null
    chosen.value=[...all.keys()]
  }catch(e){error.value=errorText(e)}
  finally{selectingAll.value=false;loading.value=false}
}
async function setSide(side:string|null){
  if(!chosen.value.length||busy.value||selectingAll.value)return
  busy.value=true
  const sam=selected.value, ids=[...chosen.value]
  try{
    let sideLabel:string|null=null
    for(let offset=0;offset<ids.length;offset+=500){
      const changed=await referenceApi.setSides(sam,ids.slice(offset,offset+500),side)
      sideLabel=changed.side
    }
    if(selected.value!==sam)return
    chosen.value=[];sideDialog.value=false
    await reset()
    notice.add(sideLabel?'Сторона назначена: '+ids.length+' фото':'Сторона снята: '+ids.length+' фото','ok')
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
function loadMoreIfNearEnd(){
  const panel=galleryScroll.value
  if(!panel||loading.value||!cursor.value||galleryError.value)return
  const remaining=window.matchMedia('(min-width:701px)').matches
    ?panel.scrollHeight-panel.scrollTop-panel.clientHeight
    :panel.getBoundingClientRect().bottom-window.innerHeight
  if(remaining<420)void load()
}
watch([loading,cursor],async()=>{
  if(!loading.value){await nextTick();loadMoreIfNearEnd()}
})
async function loadRegions(){
  try{regionRows.value=(await regionApi.list()).regions}
  catch(e){error.value=errorText(e)}
}
async function refresh(){
  try{
    const refs=await referenceApi.list()
    list.value=refs.sam
    if(!selected.value||!list.value.some(x=>x.sam===selected.value))selected.value=list.value[0]?.sam||''
    error.value=''
  }catch(e){error.value=errorText(e)}finally{listLoading.value=false}
}
watch(selected,()=>{
  viewer.value=null;selectionMode.value=false;chosen.value=[];sideDialog.value=false
  if(galleryScroll.value)galleryScroll.value.scrollTop=0
  if(selected.value)void reset();else items.value=[]
})
onMounted(()=>{window.addEventListener('scroll',loadMoreIfNearEnd,{passive:true});
  void Promise.all([refresh(),loadRegions()])})
onBeforeUnmount(()=>window.removeEventListener('scroll',loadMoreIfNearEnd))
usePolling(async()=>{
  await refresh()
  if(awaitingDeletion.value){
    await reset()
    awaitingDeletion.value=false
    return
  }
  if(!selected.value||!items.value.length)return
  const first=await referenceApi.gallery(selected.value)
  const byId=new Map(first.photos.map(x=>[x.id,x]))
  items.value=items.value.map(p=>byId.get(p.id)||p)
},8000)
async function dropOne(){
  if(!deletePhoto.value)return
  busy.value=true
  try{
    const removed=await referenceApi.remove(deletePhoto.value)
    deletePhoto.value=null
    chosen.value=[]
    if(removed.queued){awaitingDeletion.value=true;notice.add('Удаление поставлено в очередь','ok')}
    else{await refresh();await reset();notice.add('Образец удалён','ok')}
  }
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function savedConstruction(updated:UpdatedConstruction){
  editing.value=false
  selected.value=updated.sam
  await refresh()
  notice.add(updated.previous_sam===updated.sam
    ?'Данные конструкции обновлены'
    :'Конструкция переименована. Образцы сохранены.','ok')
}
function downloadAll(){
  const anchor=document.createElement('a')
  anchor.href=referenceApi.downloadAll()
  document.body.append(anchor)
  anchor.click();anchor.remove()
}
function openUpload(mode:'single'){
  uploader.launch(mode,selected.value,selectedEntry.value?.display_name||selected.value)
}
watch(()=>uploader.lastCompleted,async completion=>{
  if(!completion||'batchId' in completion)return
  await refresh()
  if(completion.sam&&list.value.some(entry=>entry.sam===completion.sam))selected.value=completion.sam
})
async function removeSam(){
  busy.value=true
  try{
    const removed=await referenceApi.deleteSam(selected.value)
    deleteSam.value=false
    if(removed.queued){awaitingDeletion.value=true;notice.add('Удаление конструкции поставлено в очередь','ok')}
    else{selected.value='';await refresh();notice.add('Конструкция и её образцы удалены','ok')}
  }
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="reference-library-view">
<PageHeader eyebrow="БИБЛИОТЕКА КОНСТРУКЦИЙ" title="Образцы">
  <template #actions>
  <UiButton :disabled="listLoading||!list.some(s=>s.photos>0)" @click="downloadAll">↓ Скачать все образцы ZIP</UiButton>
  <UiButton kind="primary" @click="uploader.launch('construction')">+ Создать конструкцию</UiButton>
</template>
</PageHeader>
<div v-if="error" class="alert error" role="alert" style="margin-bottom:18px">{{error}}</div>
<div class="toolbar row wrap between">
  <RegionPicker v-model="regionChosen" :regions="regionRows" allow-all allow-custom
    label="Выбрать регион" @created="loadRegions"/>
  <span class="meta">Всего {{list.length}} конструкций · {{list.reduce((n,s)=>n+s.photos,0)}} эталонных фото</span>
</div>
<div v-if="list.length" class="split">
  <GroupPicker v-model="selected" :items="groups" placeholder="Поиск номера или адреса…"/>
  <section class="panel split-main">
    <div class="panel-header reference-detail-header"><div><h2>{{selectedEntry?.display_name||selected}}</h2>
      <span class="meta">{{selectedEntry?.photos||0}} образцов</span></div>
      <div class="row wrap">
        <UiButton small class="reference-select-mode-toggle" :kind="selectionMode?'primary':'secondary'"
          :disabled="busy||selectingAll" :aria-pressed="selectionMode"
          @click="toggleSelectionMode">{{selectionMode?'Готово':'Выделить'}}</UiButton>
        <UiButton small @click="openUpload('single')">+ Добавить фото</UiButton>
        <UiButton small @click="editing=true">Изменить конструкцию</UiButton>
        <UiButton kind="danger" small  @click="deleteSam=true">Удалить конструкцию</UiButton>
      </div>
    </div>
    <div ref="galleryScroll" class="reference-library-gallery-scroll"
      :class="{'reference-gallery-selecting':selectionMode}" @scroll.passive="loadMoreIfNearEnd">
      <div v-if="galleryError" class="alert error">{{galleryError}}</div>
      <template v-if="items.length">
        <section v-for="group in sideGroups" :key="group.side||'unassigned'" class="reference-side-section">
          <div class="reference-side-heading" :class="{'reference-side-heading-unassigned':!group.side}">
            <div><strong>{{group.side?'Сторона '+group.side:'Неназначена сторона'}}</strong>
              <span class="meta">{{group.photos.length}} фото</span></div>

          </div>
          <VirtualThumbnailGrid :items="group.photos.map(p=>({
              id:p.id,label:p.name,side:p.side,thumbnail_status:p.thumbnail_status,
              thumbnail_url:p.thumbnail_url,original_url:p.original_url}))"
            :selected-ids="chosenSet" :selectable="selectionMode" :show-side-status="true"
            :can-delete="!selectionMode"
            @open="i=>openGroup(group.photos,i)" @remove="id=>deletePhoto=id" @toggle="togglePhoto"/>
        </section>
      </template>
      <LoadingSkeleton v-else-if="loading" variant="gallery" label="Загружаем образцы"/>
      <EmptyState v-else-if="!galleryError" title="В этой SAM пока нет фотографий"/>
      <div v-if="cursor" class="pagination"><UiButton :loading="loading" @click="load()">Показать ещё</UiButton></div>
    </div>
    <div v-if="selectionMode" class="reference-sides-toolbar" role="toolbar" aria-label="Работа с выделенными образцами">
      <strong class="reference-selection-count">Выбрано: {{chosen.length}}</strong>
      <UiButton small :loading="selectingAll" :disabled="busy||loading||!items.length||chosen.length===items.length&&cursor===null"
        @click="selectAll">Выделить все</UiButton>
      <UiButton small :disabled="busy||selectingAll||!chosen.length"
        @click="chosen=[]">Снять выделение</UiButton>
      <UiButton kind="primary" small :disabled="busy||selectingAll||!chosen.length"
        @click="sideDialog=true">Назначить сторону</UiButton>
    </div>
  </section>
</div>
<LoadingSkeleton v-else-if="listLoading" variant="split" label="Загружаем библиотеку образцов"/>
<EmptyState v-else-if="!error" title="Пока нет образцов"/>
<ImageViewer v-if="viewer!==null" :items="preview" :initial="viewer" @close="viewer=null"/>
<AssignSideDialog v-if="sideDialog" :count="chosen.length" :busy="busy"
  @assign="side=>setSide(side)" @clear="setSide(null)" @cancel="sideDialog=false"/>
<ConfirmDialog v-if="deletePhoto" title="Удалить Образец?" message="Образец будет удалён сразу или после текущих задач в очереди. Старые результаты ФО сохранятся." danger confirm-label="Удалить Образец" :busy="busy" @cancel="deletePhoto=null" @confirm="dropOne"/>
<ConfirmDialog v-if="deleteSam" title="Безвозвратно удалить конструкцию?" :message="'Все эталонные фото '+selected+' будут удалены из общей библиотеки. Это не удаляет партии ФО.'" :required-text="selected" danger confirm-label="Удалить SAM" :busy="busy" @cancel="deleteSam=false" @confirm="removeSam"/>
<EditConstructionDialog v-if="editing&&selectedEntry" :key="selectedEntry.sam"
  :entry="selectedEntry" @dismiss="editing=false" @saved="savedConstruction"/>
</div>
</template>
