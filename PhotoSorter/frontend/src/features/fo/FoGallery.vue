<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {batchApi} from '../../api/batches'
import type {Batch,Photo} from '../../types/api'
import {useCursor} from '../../composables/useCursor'
import {usePolling} from '../../composables/usePolling'
import {date,bytes,errorText} from '../../utils/format'
import {useNoticeStore} from '../../stores/notice'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
import VirtualThumbnailGrid from '../../components/gallery/VirtualThumbnailGrid.vue'
import ImageViewer from '../../components/gallery/ImageViewer.vue'
const route=useRoute(),router=useRouter(),notice=useNoticeStore()
const id=String(route.params.batchId)
const batch=ref<Batch|null>(null),count=ref<{total:number;ready:number;failed:number}|null>(null)
const rename=ref(false),newName=ref(''),busy=ref(false),error=ref('')
const deleteWhole=ref(false),deletePhoto=ref<string|null>(null),viewer=ref<number|null>(null)
const {items,cursor,loading,error:galleryError,load,reset}=useCursor<Photo>(next=>batchApi.gallery(id,next))
const preview=computed(()=>items.value.map(p=>({src:p.original_url||'',label:p.name})))
const readyPercent=computed(()=>count.value?.total?Math.round(count.value.ready/count.value.total*100):0)
async function refresh(){
  try{batch.value=await batchApi.one(id);count.value=await batchApi.thumbs(id)}
  catch(e){error.value=errorText(e)}
}
const {refresh:tick}=usePolling(async()=>{
  if(!batch.value||batch.value.delete_state!=='active')return
  const prior=count.value?.ready||0
  count.value=await batchApi.thumbs(id)
  if(count.value.ready>prior && items.value.length){
    const next=await batchApi.gallery(id)
    const map=new Map(next.photos.map(p=>[p.id,p]))
    items.value=items.value.map(p=>map.get(p.id)||p)
  }
},7000)
onMounted(async()=>{await Promise.all([refresh(),reset()])})
async function saveName(){
  if(!newName.value.trim())return
  busy.value=true
  try{batch.value=await batchApi.rename(id,newName.value.trim());rename.value=false;notice.add('Партия переименована','ok')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function removePhoto(){
  if(!deletePhoto.value)return
  busy.value=true
  try{await batchApi.removePhoto(id,deletePhoto.value);deletePhoto.value=null;await Promise.all([refresh(),reset()]);notice.add('ФО удалено','ok')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function removeBatch(){
  busy.value=true
  try{await batchApi.remove(id);deleteWhole.value=false;notice.add('Партия поставлена на безопасное удаление','ok');await router.push('/fo')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="row" style="margin-bottom:22px"><RouterLink to="/fo" class="meta">← Все фотоотчёты</RouterLink></div>
<PageHeader :title="batch?.display_name||'Галерея партии'" :subtitle="batch?date(batch.created_at)+' · '+(batch.photos??'—')+' ФО · '+bytes(batch.size_bytes):'Загрузка…'" eyebrow="ФО / ПАРТИЯ">
  <template #actions><UiButton @click="newName=batch?.display_name||'';rename=true">Переименовать</UiButton><UiButton kind="danger" @click="deleteWhole=true">Удалить всю партию</UiButton></template>
</PageHeader>
<div v-if="error" class="alert error" role="alert">{{error}}</div>
<section v-if="count" class="panel stack-sm" style="margin-bottom:19px">
  <div class="row between"><span>Подготовка миниатюр</span><span class="meta">{{count.ready}} / {{count.total}} · {{readyPercent}}%</span></div>
  <div class="progress-track" role="progressbar" :aria-valuenow="readyPercent" aria-valuemin="0" aria-valuemax="100"><span class="progress-fill" :style="{width:readyPercent+'%'}"/></div>
  <div class="meta">{{count.failed?'Не удалось создать '+count.failed+' миниатюр.':''}} Оригиналы доступны независимо от превью.</div>
</section>
<div v-if="batch&&batch.runs" class="alert" style="margin-bottom:20px">Эта партия уже обрабатывалась. Удаление отдельного ФО заблокировано, чтобы не нарушить существующие результаты.</div>
<div v-if="galleryError" class="alert error">{{galleryError}}</div>
<VirtualThumbnailGrid v-if="items.length" :items="items.map(p=>({id:p.id,label:p.name,thumbnail_url:p.thumbnail_url,original_url:p.original_url,thumbnail_status:p.thumbnail_status}))"
  :can-delete="!batch?.runs&&batch?.delete_state==='active'" @open="i=>viewer=i" @remove="pid=>deletePhoto=pid"/>
<div v-else-if="!loading" class="empty"><strong>В этой партии пока нет фото</strong><p>Вернитесь к списку и выберите папку для загрузки.</p></div>
<div v-if="cursor" class="pagination"><UiButton :loading="loading" @click="load()">Показать ещё фотографии</UiButton></div>
<ImageViewer v-if="viewer!==null" :items="preview" :initial="viewer" @close="viewer=null"/>
<div v-if="rename" class="modal-overlay" @click.self="rename=false">
  <form class="modal stack" @submit.prevent="saveName" role="dialog" aria-modal="true" aria-label="Переименование партии">
    <h2>Переименовать партию</h2><p>Оригиналы ФО и результаты останутся на месте.</p>
    <label class="field">Название<input v-model="newName" maxlength="120" minlength="1" required autofocus/></label>
    <div class="modal-actions"><UiButton @click="rename=false">Отмена</UiButton><UiButton kind="primary" type="submit" :loading="busy">Сохранить</UiButton></div>
  </form>
</div>
<ConfirmDialog v-if="deletePhoto" title="Удалить фотографию?" message="Удаление невозможно отменить. Операция доступна только до начала сортировки." confirm-label="Удалить ФО" :danger="true" :busy="busy" @confirm="removePhoto" @cancel="deletePhoto=null"/>
<ConfirmDialog v-if="deleteWhole&&batch" title="Безвозвратно удалить всю партию?" :message="'Будут удалены ВСЕ фотографии, запуски, результаты и логи партии «'+batch.display_name+'». Общие Образцы и модель не затрагиваются.'" confirm-label="Удалить всю партию" :required-text="batch.display_name" :danger="true" :busy="busy" @confirm="removeBatch" @cancel="deleteWhole=false"/>
</template>
