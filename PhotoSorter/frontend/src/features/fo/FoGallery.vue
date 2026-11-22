<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {batchApi} from '../../api/batches'
import {runApi} from '../../api/runs'
import {batchProcessing,batchThreshold} from '../../utils/batchProcessing'
import type {Batch,Photo} from '../../types/api'
import {useCursor} from '../../composables/useCursor'
import {usePolling} from '../../composables/usePolling'
import {date,bytes,errorText,isActive,readyToStart} from '../../utils/format'
import {useNoticeStore} from '../../stores/notice'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {useDeletionStore} from '../../stores/deletion'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
import VirtualThumbnailGrid from '../../components/gallery/VirtualThumbnailGrid.vue'
import ImageViewer from '../../components/gallery/ImageViewer.vue'
import type {ViewerItem} from '../../components/gallery/ImageViewer.vue'
import PendingUploads from './PendingUploads.vue'
import BatchProcessingStatus from './BatchProcessingStatus.vue'
import BatchRunHistory from './BatchRunHistory.vue'
import StartRegionsDialog from './StartRegionsDialog.vue'
const route=useRoute(),router=useRouter(),notice=useNoticeStore(),deletion=useDeletionStore()
const id=String(route.params.batchId)
const uploader=useUploadCenterStore()
const transfer=computed(()=>uploader.rows.find(row=>row.batchId===id))
const batch=ref<Batch|null>(null),count=ref<{total:number;ready:number;failed:number}|null>(null)
const rename=ref(false),newName=ref(''),busy=ref(false),error=ref('')
const deleteWhole=ref(false),deletePhoto=ref<string|null>(null),viewer=ref<number|null>(null)
const stopConfirm=ref(false),showHistory=ref(false),historyKey=ref(0),regionStart=ref(false)
const processing=computed(()=>batch.value?batchProcessing(batch.value):null)
const {items,cursor,loading,error:galleryError,load,reset}=useCursor<Photo>(next=>batchApi.gallery(id,next))
const preview=computed<ViewerItem[]>(()=>items.value.map(p=>{
  const video=p.media_kind==='video'||!!p.original_media_type?.startsWith('video/')
  const poster=p.thumbnail_status==='ready'?p.thumbnail_url:null
  const original=p.preview_url||(!p.original_media_type?p.original_url:null)
  const prepared=p.play_url||null
  const preparing=!p.media_error&&batch.value?.delete_state==='active'&&
    ['queued','running'].includes(batch.value.media_preparation?.state??'')
  return {
    src:prepared||original||(!video?poster:null)||'',label:p.name,video,poster,
    fallbackMessage:p.media_error
      ?'Не удалось подготовить файл для просмотра.'
      :preparing?'Полный просмотр будет доступен после перекодирования.'
      :video?'Браузер не смог воспроизвести этот формат.':'Полноразмерный просмотр этого формата недоступен.',
    previewOnly:!video&&!prepared&&!original&&!!poster,
  }
}))
const mediaErrors=ref<{id:string;filename:string;media_error:string}[]>([])
const showMediaErrors=ref(false)
async function inspectMedia(){
  if(showMediaErrors.value){showMediaErrors.value=false;return}
  try{mediaErrors.value=(await batchApi.mediaErrors(id)).files;showMediaErrors.value=true}
  catch(e){error.value=errorText(e)}
}
async function retryMedia(){
  busy.value=true
  try{await batchApi.retryMedia(id);showMediaErrors.value=false;await refresh()}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
const initialGallery=ref(true)
const readyPercent=computed(()=>count.value?.total?Math.round(count.value.ready/count.value.total*100):0)
async function refresh(){
  try{batch.value=await batchApi.one(id);count.value=await batchApi.thumbs(id)}
  catch(e){error.value=errorText(e)}
}
usePolling(async()=>{
  if(!batch.value||batch.value.delete_state!=='active')return
  const prior=count.value?.ready||0
  count.value=await batchApi.thumbs(id)
  if(count.value.ready>prior && items.value.length){
    const next=await batchApi.gallery(id)
    const map=new Map(next.photos.map(p=>[p.id,p]))
    items.value=items.value.map(p=>map.get(p.id)||p)
  }
},4500)
usePolling(async()=>{
  if(batch.value?.delete_state==='active'){
    const media=batch.value.media_preparation
    batch.value=await batchApi.one(id)
    const nextMedia=batch.value.media_preparation
    if((media?.state!==nextMedia?.state||media?.completed_count!==nextMedia?.completed_count)&&batch.value.media_image_format){
      const next=await batchApi.gallery(id,undefined,Math.min(200,Math.max(60,items.value.length)))
      const changed=new Map(next.photos.map(p=>[p.id,p]))
      items.value=items.value.map(p=>changed.get(p.id)||p)
    }
  }
},()=>isActive(batch.value?.latest_run?.status)||['queued','running'].includes(batch.value?.media_preparation?.state??'')?1000:4500)
onMounted(async()=>{try{await Promise.all([refresh(),reset()])}finally{initialGallery.value=false}})
async function onPendingChanged(){await Promise.all([refresh(),reset()])}
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
async function startRun(codes:string[]){
  if(!batch.value||!processing.value?.canStart||busy.value)return
  busy.value=true;error.value=''
  try{
    const created=await runApi.start(id,batchThreshold(batch.value),codes)
    regionStart.value=false
    notice.add(readyToStart(created)?'Запуск обработки MegaLoc':'MegaLoc добавлен в очередь','ok')
    await refresh();historyKey.value++
  }catch(e){error.value=errorText(e);await refresh()}finally{busy.value=false}
}
async function stopRun(){
  if(!processing.value?.run||busy.value)return
  const current=processing.value.run
  busy.value=true;error.value=''
  try{
    await runApi.stop(current.id)
    stopConfirm.value=false
    notice.add(current.status==='queued'?'Задание убрано из очереди':'Запрошена остановка MegaLoc','ok')
    await refresh();historyKey.value++
  }catch(e){error.value=errorText(e);await refresh()}finally{busy.value=false}
}
async function cancelAuto(){
  if(busy.value)return
  busy.value=true;error.value=''
  try{await batchApi.cancelAutomatic(id);notice.add('Автозапуск отменён','ok');await refresh()}
  catch(e){error.value=errorText(e);await refresh()}finally{busy.value=false}
}
async function removeBatch(){
  busy.value=true
  deletion.mark(id,batch.value?.display_name||id)
  try{await batchApi.remove(id);deleteWhole.value=false;notice.add('Партия поставлена на безопасное удаление','ok');await router.push('/fo')}
  catch(e){deletion.clear(id);error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="row" style="margin-bottom:22px"><RouterLink to="/fo" class="meta">← Все фотоотчёты</RouterLink></div>
<PageHeader :title="batch?.display_name||'Галерея партии'" :subtitle="batch?date(batch.created_at)+' · '+(batch.photos??'—')+' фото'+(batch.videos?' · '+batch.videos+' видео':'')+(batch.media_files?' · '+batch.media_files+(batch.media_image_format?' ошибок подготовки':' без сортировки'):'')+' · '+bytes(batch.size_bytes):'Загрузка…'" eyebrow="ФО / ПАРТИЯ">
  <template #actions><UiButton @click="newName=batch?.display_name||'';rename=true">Переименовать</UiButton><UiButton kind="danger" @click="deleteWhole=true">Удалить всю партию</UiButton></template>
</PageHeader>
<div v-if="error" class="alert error" role="alert">{{error}}</div>
<section v-if="batch" class="panel stack" :class="{'deletion-panel':deletion.pending(id)||batch.delete_state==='deleting'}" style="margin-bottom:19px" aria-label="Обработка MegaLoc для партии">
  <div class="row between wrap"><h2 style="margin:0">Обработка MegaLoc</h2><span class="meta">Миниатюры и сортировка — независимые процессы</span></div>
  <div v-if="deletion.pending(id)||batch.delete_state==='deleting'" class="deletion-state">Удаляется · удаление файлов и результатов</div>
  <BatchProcessingStatus v-else :batch="batch" :transfer="transfer"/>
  <div v-if="batch.media_files&&batch.media_image_format" class="alert warning row wrap between">
    <span>Файлов без готовой копии: {{batch.media_files}}. Они не попадут в ZIP.</span>
    <UiButton small @click="inspectMedia">{{showMediaErrors?'Скрыть ошибки':'Показать ошибки'}}</UiButton>
  </div>
  <ul v-if="showMediaErrors" class="meta">
    <li v-for="file in mediaErrors" :key="file.id">{{file.filename}} — {{file.media_error}}</li>
  </ul>
  <div class="row wrap fo-batch-actions">
    <UiButton v-if="['failed','interrupted','completed_with_errors'].includes(batch.media_preparation?.state??'')&&!processing?.canStop"
      small :loading="busy" @click="retryMedia">Повторить перекодирование</UiButton>
    <UiButton v-if="!transfer&&processing?.canStart" kind="primary" small :loading="busy" @click="regionStart=true">{{(batch.runs??0)>0?'Повторить обработку':'Обработать'}}</UiButton>
    <UiButton v-if="processing?.canCancelAuto" small :loading="busy" @click="cancelAuto">Отменить автозапуск</UiButton>
    <UiButton v-if="processing?.canStop" small kind="danger" :loading="busy" @click="stopConfirm=true">
      {{processing?.run?.status==='queued'?'Убрать из очереди':'Остановить'}}
    </UiButton>
    <RouterLink v-if="processing?.run" :to="'/queue/runs/'+processing.run.id" class="btn small">Подробности запуска</RouterLink>
    <RouterLink v-if="processing?.resultId" :to="'/results/'+processing.resultId" class="btn small">{{processing.run?.id===processing.resultId?'Результаты':'Прошлые результаты'}}</RouterLink>
    <UiButton v-if="(batch.runs??0)>0" small @click="showHistory=!showHistory">{{showHistory?'Скрыть историю':'История запусков ('+batch.runs+')'}}</UiButton>
  </div>
</section>
<BatchRunHistory v-if="showHistory&&batch&&(batch.runs??0)>0" :key="id+'-'+historyKey" :batch-id="id" style="margin-bottom:19px"/>
<PendingUploads v-if="batch?.delete_state==='active'" :batch-id="id" :batch-name="batch.display_name" :disabled="!!batch.runs" @changed="onPendingChanged"/>
<section v-if="count&&(count.total||!batch?.media_files)" class="panel stack-sm" style="margin-bottom:19px">
  <div class="row between"><span>{{transfer?'Миниатюры сохранённых файлов':'Подготовка миниатюр'}}</span><span class="meta">{{count.ready}} / {{count.total}} · {{readyPercent}}%</span></div>
  <div class="progress-track" role="progressbar" :aria-valuenow="readyPercent" aria-valuemin="0" aria-valuemax="100"><span class="progress-fill" :style="{width:readyPercent+'%'}"/></div>
  <div class="meta">{{count.failed?'Не удалось создать '+count.failed+' миниатюр.':''}} Оригиналы доступны независимо от превью.</div>
</section>
<div v-if="batch&&batch.runs" class="alert" style="margin-bottom:20px">Эта партия уже обрабатывалась. Удаление отдельного ФО заблокировано, чтобы не нарушить существующие результаты.</div>
<div v-if="galleryError" class="alert error">{{galleryError}}</div>
<VirtualThumbnailGrid v-if="items.length" :items="items.map(p=>({...p,label:p.name}))"
  :can-delete="!batch?.runs&&batch?.delete_state==='active'&&!['queued','running','failed','interrupted'].includes(batch.media_preparation?.state??'')" @open="i=>viewer=i" @remove="pid=>deletePhoto=pid"/>
<LoadingSkeleton v-else-if="loading||initialGallery" variant="gallery" label="Загружаем фотографии"/>
<EmptyState v-else-if="!galleryError" title="В этой партии пока нет фото"/>
<div v-if="cursor" class="pagination"><UiButton :loading="loading" @click="load()">Показать ещё фотографии</UiButton></div>
<StartRegionsDialog v-if="regionStart" :busy="busy" @confirm="startRun" @cancel="regionStart=false"/>
<ImageViewer v-if="viewer!==null" :items="preview" :initial="viewer" @close="viewer=null"/>
<div v-if="rename" class="modal-overlay" @click.self="rename=false">
  <form class="modal stack" @submit.prevent="saveName" role="dialog" aria-modal="true" aria-label="Переименование партии">
    <h2>Переименовать партию</h2><p>Оригиналы ФО и результаты останутся на месте.</p>
    <label class="field">Название<input v-model="newName" maxlength="120" minlength="1" required autofocus/></label>
    <div class="modal-actions"><UiButton @click="rename=false">Отмена</UiButton><UiButton kind="primary" type="submit" :loading="busy">Сохранить</UiButton></div>
  </form>
</div>
<ConfirmDialog v-if="stopConfirm&&processing?.run" :title="processing.run.status==='queued'?'Убрать задание из очереди?':'Остановить MegaLoc?'"
  message="Фотографии и история других запусков сохранятся. Остановка текущей обработки может прервать незавершённый результат."
  :danger="true" :busy="busy" :confirm-label="processing.run.status==='queued'?'Убрать из очереди':'Остановить'"
  @cancel="stopConfirm=false" @confirm="stopRun"/>
<ConfirmDialog v-if="deletePhoto" title="Удалить фотографию?" message="Удаление невозможно отменить. Операция доступна только до начала сортировки." confirm-label="Удалить ФО" :danger="true" :busy="busy" @confirm="removePhoto" @cancel="deletePhoto=null"/>
<ConfirmDialog v-if="deleteWhole&&batch" title="Безвозвратно удалить всю партию?" :message="'Будут удалены ВСЕ фотографии, запуски, результаты и логи партии «'+batch.display_name+'». Общие Образцы и модель не затрагиваются.'" confirm-label="Удалить всю партию" :required-text="batch.display_name" :danger="true" :busy="busy" @confirm="removeBatch" @cancel="deleteWhole=false"/>
</template>
