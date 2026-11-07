<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {referenceApi} from '../../api/references'
import {libraryNoticesApi} from '../../api/libraryNotices'
import type {LibraryStatus} from '../../api/libraryNotices'
import ReferencePreparationStatus from './ReferencePreparationStatus.vue'
import {runApi} from '../../api/runs'
import {useCursor} from '../../composables/useCursor'
import {usePolling} from '../../composables/usePolling'
import {useNoticeStore} from '../../stores/notice'
import type {Photo,SamCount} from '../../types/api'
import {errorText,isActive} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
import GroupPicker from '../../components/split/GroupPicker.vue'
import VirtualThumbnailGrid from '../../components/gallery/VirtualThumbnailGrid.vue'
import ImageViewer from '../../components/gallery/ImageViewer.vue'
import ReferenceUploader from './ReferenceUploader.vue'
const list=ref<SamCount[]>([]),selected=ref(''),adding=ref(false),editing=ref(false),addressDraft=ref(''),
  uploadMode=ref<'library'|'single'>('library'),
  error=ref(''),busy=ref(false),active=ref(false),viewer=ref<number|null>(null),
  deletePhoto=ref<string|null>(null),deleteSam=ref(false),
  cache=ref<{total:number;cached:number;current_signature?:string|null}|null>(null),
  library=ref<LibraryStatus|null>(null),modeReady=ref(false)
const notice=useNoticeStore()
const groups=computed(()=>list.value.map(s=>({id:s.sam,label:s.display_name||s.sam,count:s.photos})))
const selectedEntry=computed(()=>list.value.find(item=>item.sam===selected.value))
const {items,cursor,loading,error:galleryError,load,reset}=useCursor<Photo>(cursor=>referenceApi.gallery(selected.value,cursor))
const preview=computed(()=>items.value.map(p=>({src:p.original_url||'',label:p.name})))
async function refresh(){
  try{
    const [refs,runs,cacheValue,lib]=await Promise.all([
      referenceApi.list(),runApi.list(100),referenceApi.cache().catch(()=>null),
      libraryNoticesApi.status()
    ])
    list.value=refs.sam;active.value=runs.runs.some(r=>isActive(r.status))
    cache.value=cacheValue;library.value=lib;modeReady.value=true
    if(!selected.value||!list.value.some(x=>x.sam===selected.value))selected.value=list.value[0]?.sam||''
    error.value=''
  }catch(e){error.value=errorText(e);modeReady.value=false}
}
watch(selected,()=>{viewer.value=null;if(selected.value)void reset();else items.value=[]})
onMounted(()=>{void refresh()})
usePolling(async()=>{
  await refresh()
  if(!selected.value||!items.value.length)return
  const first=await referenceApi.gallery(selected.value)
  const byId=new Map(first.photos.map(x=>[x.id,x]))
  items.value=items.value.map(p=>byId.get(p.id)||p)
},8000)
async function dropOne(){
  if(!deletePhoto.value)return
  busy.value=true
  try{await referenceApi.remove(deletePhoto.value);deletePhoto.value=null;await refresh();await reset();notice.add('Образец удалён','ok')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function saveAddress(){
  busy.value=true
  try{
    await referenceApi.changeAddress(selected.value,addressDraft.value)
    editing.value=false
    await refresh()
    notice.add('Адрес изменён. Номер конструкции и её образцы не затронуты.','ok')
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
function openUpload(mode:'library'|'single'){
  uploadMode.value=mode
  adding.value=true
}
async function onUploaded(){
  adding.value=false
  await refresh()
  if(selected.value)await reset()
}
async function removeSam(){
  busy.value=true
  try{await referenceApi.deleteSam(selected.value);deleteSam.value=false;selected.value='';await refresh();notice.add('Конструкция и её образцы удалены','ok')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<PageHeader eyebrow="БИБЛИОТЕКА КОНСТРУКЦИЙ" title="Образцы" subtitle="Одна постоянная библиотека для всех фотоотчётов.">
  <template #actions><UiButton kind="primary" :disabled="!modeReady||(active&&!library?.staged_imports_enabled)" @click="adding?adding=false:openUpload('library')">{{adding?'Закрыть загрузку':'+ Загрузить образцы'}}</UiButton></template>
</PageHeader>
<div v-if="error" class="alert error" role="alert" style="margin-bottom:18px">{{error}}</div>
<ReferenceUploader v-if="adding" :selected-sam="selected" :selected-label="selectedEntry?.display_name||selected"
  :initial-mode="uploadMode" :staged="library?.staged_imports_enabled"
  :disabled="!modeReady||(active&&!library?.staged_imports_enabled)" style="margin-bottom:20px" @finished="onUploaded"/>
<div v-if="active&&!library?.staged_imports_enabled" class="alert" style="margin-bottom:18px">
  Загрузка образцов доступна после завершения текущих и ожидающих обработок. Новый
  способ независимой загрузки пока выключен.
</div>
<ReferencePreparationStatus :library="library" style="margin-bottom:17px"/>
<div class="row wrap between" style="margin-bottom:17px">
  <span class="meta">Всего {{list.length}} конструкций · {{list.reduce((n,s)=>n+s.photos,0)}} эталонных фото</span>
  <span v-if="cache" class="meta">Кэш MegaLoc: {{cache.cached}} / {{cache.total}} · {{cache.current_signature?'актуальная подпись':'модель не подтверждена'}}</span>
</div>
<div v-if="list.length" class="split">
  <GroupPicker v-model="selected" :items="groups" placeholder="Поиск номера или адреса…"/>
  <section class="panel split-main">
    <div class="panel-header reference-detail-header"><div><h2>{{selectedEntry?.display_name||selected}}</h2>
      <span class="meta">{{selectedEntry?.photos||0}} образцов</span></div>
      <div class="row wrap">
        <UiButton small :disabled="!modeReady||(active&&!library?.staged_imports_enabled)" @click="openUpload('single')">+ Добавить фото</UiButton>
        <UiButton v-if="selectedEntry?.address!=null" small :disabled="active"
          @click="addressDraft=selectedEntry.address||'';editing=true">Изменить адрес</UiButton>
        <UiButton kind="danger" small :disabled="active" @click="deleteSam=true">Удалить конструкцию</UiButton>
      </div>
    </div>
    <div v-if="galleryError" class="alert error">{{galleryError}}</div>
    <VirtualThumbnailGrid v-if="items.length" :items="items.map(p=>({id:p.id,label:p.name,thumbnail_status:p.thumbnail_status,thumbnail_url:p.thumbnail_url,original_url:p.original_url}))" :can-delete="!active" @open="i=>viewer=i" @remove="id=>deletePhoto=id"/>
    <EmptyState v-else-if="!loading" title="В этой SAM пока нет фотографий" detail="Добавьте эталонные фото для сопоставления."/>
    <div v-if="cursor" class="pagination"><UiButton :loading="loading" @click="load()">Показать ещё</UiButton></div>
  </section>
</div>
<EmptyState v-else title="Библиотека Образцов пуста" detail="Выберите библиотеку с папками вида SAM 0004 — Гагарина 64. Перед отправкой будет полная проверка.">
  <UiButton kind="primary" @click="openUpload('library')">Загрузить библиотеку</UiButton>
</EmptyState>
<ImageViewer v-if="viewer!==null" :items="preview" :initial="viewer" @close="viewer=null"/>
<ConfirmDialog v-if="deletePhoto" title="Удалить Образец?" message="Фотография исчезнет из общей библиотеки SAM. Действующие обработки остаются, пока нет активных запусков." danger confirm-label="Удалить Образец" :busy="busy" @cancel="deletePhoto=null" @confirm="dropOne"/>
<ConfirmDialog v-if="deleteSam" title="Безвозвратно удалить конструкцию?" :message="'Все эталонные фото '+selected+' будут удалены из общей библиотеки. Это не удаляет партии ФО.'" :required-text="selected" danger confirm-label="Удалить SAM" :busy="busy" @cancel="deleteSam=false" @confirm="removeSam"/>
<div v-if="editing" class="modal-overlay" @click.self="editing=false">
  <form class="modal stack" @submit.prevent="saveAddress">
    <h2>Изменить адрес</h2><p>Номер {{selected}} и все фотографии останутся прежними.</p>
    <label class="field">Адрес конструкции<input v-model="addressDraft" required maxlength="120"/></label>
    <div class="modal-actions"><UiButton @click="editing=false">Отмена</UiButton><UiButton kind="primary" type="submit" :loading="busy">Сохранить</UiButton></div>
  </form>
</div>
</template>
