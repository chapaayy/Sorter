<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,ref,watch} from 'vue'
import {referenceApi,type UpdatedConstruction} from '../../api/references'
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
const list=ref<SamCount[]>([]),selected=ref(''),editing=ref(false),
  error=ref(''),busy=ref(false),viewer=ref<number|null>(null),
  deletePhoto=ref<string|null>(null),deleteSam=ref(false)

const notice=useNoticeStore(),uploader=useUploadCenterStore()
const galleryScroll=ref<HTMLElement|null>(null)
const chosen=ref<string[]>([]),sideName=ref('')
const chosenSet=computed(()=>new Set(chosen.value))
const viewerItems=ref<Photo[]>([])
const awaitingDeletion=ref(false)
const listLoading=ref(true)
const groups=computed(()=>list.value.map(s=>({id:s.sam,label:s.display_name||s.sam,count:s.photos})))
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
function toggleGroup(photos:Photo[]){
  const ids=photos.map(x=>x.id)
  const chosenNow=chosenSet.value
  chosen.value=ids.every(id=>chosenNow.has(id))
    ?chosen.value.filter(id=>!ids.includes(id))
    :[...new Set([...chosen.value,...ids])]
}
async function setSide(side:string|null){
  if(!chosen.value.length||busy.value)return
  busy.value=true
  try{
    const changed=await referenceApi.setSides(selected.value,chosen.value,side)
    const count=chosen.value.length
    chosen.value=[];sideName.value=''
    await reset()
    notice.add(changed.side?'Сторона назначена: '+count+' фото':'Сторона снята: '+count+' фото','ok')
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
async function refresh(){
  try{
    const refs=await referenceApi.list()
    list.value=refs.sam
    if(!selected.value||!list.value.some(x=>x.sam===selected.value))selected.value=list.value[0]?.sam||''
    error.value=''
  }catch(e){error.value=errorText(e)}finally{listLoading.value=false}
}
watch(selected,()=>{
  viewer.value=null;chosen.value=[];sideName.value=''
  if(galleryScroll.value)galleryScroll.value.scrollTop=0
  if(selected.value)void reset();else items.value=[]
})
onMounted(()=>{window.addEventListener('scroll',loadMoreIfNearEnd,{passive:true});void refresh()})
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
<div class="toolbar">
  <span class="meta">Всего {{list.length}} конструкций · {{list.reduce((n,s)=>n+s.photos,0)}} эталонных фото</span>
</div>
<div v-if="list.length" class="split">
  <GroupPicker v-model="selected" :items="groups" placeholder="Поиск номера или адреса…"/>
  <section class="panel split-main">
    <div class="panel-header reference-detail-header"><div><h2>{{selectedEntry?.display_name||selected}}</h2>
      <span class="meta">{{selectedEntry?.photos||0}} образцов</span></div>
      <div class="row wrap">
        <UiButton small  @click="openUpload('single')">+ Добавить фото</UiButton>
        <UiButton small @click="editing=true">Изменить конструкцию</UiButton>
        <UiButton kind="danger" small  @click="deleteSam=true">Удалить конструкцию</UiButton>
      </div>
    </div>
    <div ref="galleryScroll" class="reference-library-gallery-scroll" @scroll.passive="loadMoreIfNearEnd">
      <div v-if="chosen.length" class="reference-sides-toolbar">
        <strong>Выбрано: {{chosen.length}}</strong>
        <input v-model="sideName" aria-label="Название стороны" maxlength="60"
          list="available-reference-sides" placeholder="Сторона: А, Б, А1…"
          @keydown.enter.prevent="setSide(sideName)"/>
        <datalist id="available-reference-sides">
          <option v-for="group in sideGroups.filter(g=>g.side)" :key="group.side" :value="group.side"/>
        </datalist>
        <UiButton kind="primary" small :loading="busy" :disabled="!sideName.trim()"
          @click="setSide(sideName)">Назначить сторону</UiButton>
        <UiButton small :disabled="busy" @click="setSide(null)">Снять сторону</UiButton>
        <UiButton small @click="chosen=[]">Отмена</UiButton>
      </div>
      <div v-if="galleryError" class="alert error">{{galleryError}}</div>
      <template v-if="items.length">
        <section v-for="group in sideGroups" :key="group.side||'unassigned'" class="reference-side-section">
          <div class="reference-side-heading" :class="{'reference-side-heading-unassigned':!group.side}">
            <div><strong>{{group.side?'Сторона '+group.side:'Неназначена сторона'}}</strong>
              <span class="meta">{{group.photos.length}} фото</span></div>
            <UiButton small @click="toggleGroup(group.photos)">
              {{group.photos.every(p=>chosenSet.has(p.id))?'Снять выделение':'Выбрать фото'}}
            </UiButton>
          </div>
          <VirtualThumbnailGrid :items="group.photos.map(p=>({
              id:p.id,label:p.name,side:p.side,thumbnail_status:p.thumbnail_status,
              thumbnail_url:p.thumbnail_url,original_url:p.original_url}))"
            :selected-ids="chosenSet" :selectable="true" :show-side-status="true" :can-delete="true"
            @open="i=>openGroup(group.photos,i)" @remove="id=>deletePhoto=id" @toggle="togglePhoto"/>
        </section>
      </template>
      <LoadingSkeleton v-else-if="loading" variant="gallery" label="Загружаем образцы"/>
      <EmptyState v-else-if="!galleryError" title="В этой SAM пока нет фотографий"/>
      <div v-if="cursor" class="pagination"><UiButton :loading="loading" @click="load()">Показать ещё</UiButton></div>
    </div>
  </section>
</div>
<LoadingSkeleton v-else-if="listLoading" variant="split" label="Загружаем библиотеку образцов"/>
<EmptyState v-else-if="!error" title="Пока нет образцов"/>
<ImageViewer v-if="viewer!==null" :items="preview" :initial="viewer" @close="viewer=null"/>
<ConfirmDialog v-if="deletePhoto" title="Удалить Образец?" message="Образец будет удалён сразу или после текущих задач в очереди. Старые результаты ФО сохранятся." danger confirm-label="Удалить Образец" :busy="busy" @cancel="deletePhoto=null" @confirm="dropOne"/>
<ConfirmDialog v-if="deleteSam" title="Безвозвратно удалить конструкцию?" :message="'Все эталонные фото '+selected+' будут удалены из общей библиотеки. Это не удаляет партии ФО.'" :required-text="selected" danger confirm-label="Удалить SAM" :busy="busy" @cancel="deleteSam=false" @confirm="removeSam"/>
<EditConstructionDialog v-if="editing&&selectedEntry" :key="selectedEntry.sam"
  :entry="selectedEntry" @dismiss="editing=false" @saved="savedConstruction"/>
</div>
</template>
