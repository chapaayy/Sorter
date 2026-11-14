<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {batchApi} from '../../api/batches'
import type {PendingUpload,BatchUploadManifest} from '../../types/api'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {bytes,errorText} from '../../utils/format'
import {usePolling} from '../../composables/usePolling'
import UiButton from '../../components/ui/UiButton.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'

const props=defineProps<{batchId:string;disabled?:boolean}>()
const emit=defineEmits<{(e:'changed'):void}>()
const items=ref<PendingUpload[]>([]),manifest=ref<BatchUploadManifest|null>(null),loading=ref(true),error=ref('')
const activeId=ref(''),activeStatus=ref(''),confirmCancel=ref<PendingUpload|null>(null)
const errors=ref<Record<string,string>>({})
const uploader=useUploadCenterStore()
const job=uploader.windows.fo
const batchUploading=computed(()=>job.busy&&job.batchId===props.batchId)

async function refreshManifest(){
  // The pending-upload recovery UI must still work if manifest inspection
  // temporarily fails or an older API mock does not expose this endpoint.
  try{manifest.value=await batchApi.manifest(props.batchId)}
  catch{manifest.value=null}
}
async function load(autoFinish=false){
  if(activeId.value)return
  try{
    const result=await batchApi.pending(props.batchId)
    items.value=result.uploads
    await refreshManifest()
    error.value=''
    if(autoFinish&&!props.disabled&&!batchUploading.value){
      // Fully transferred bytes are safe to finalize with no local file input.
      for(const item of result.uploads.filter(upload=>upload.can_finalize)){
        if(activeId.value)break
        await finish(item,true)
      }
    }
  }catch(err){error.value='Не удалось проверить незавершённые файлы: '+errorText(err)}
  finally{loading.value=false}
}
async function finish(item:PendingUpload,automatic=false){
  if(activeId.value||props.disabled||batchUploading.value)return
  activeId.value=item.id;activeStatus.value='Проверка и сохранение файла…'
  try{
    await batchApi.finishPending(item.id)
    delete errors.value[item.id]
    items.value=(await batchApi.pending(props.batchId)).uploads
    await refreshManifest()
    emit('changed')
  }catch(err){
    errors.value[item.id]=(automatic?'Автозавершение: ':'')+errorText(err)
  }finally{activeId.value='';activeStatus.value=''}
}
function pick(item:PendingUpload){
  if(job.busy){uploader.show('fo');return}
  document.getElementById('pending-source-'+item.id)?.click()
}
function continueFile(item:PendingUpload,event:Event){
  const input=event.target as HTMLInputElement
  const file=input.files?.item(0)
  input.value=''
  if(!file||activeId.value||props.disabled)return
  delete errors.value[item.id]
  uploader.resume({batchId:props.batchId,item,file})
}
async function cancel(){
  const item=confirmCancel.value
  if(!item||activeId.value||props.disabled||batchUploading.value)return
  activeId.value=item.id;activeStatus.value='Отменяем незавершённую передачу…'
  try{
    await batchApi.cancelPending(item.id)
    confirmCancel.value=null
    delete errors.value[item.id]
    items.value=(await batchApi.pending(props.batchId)).uploads
    await refreshManifest()
    emit('changed')
  }catch(err){errors.value[item.id]=errorText(err)}
  finally{activeId.value='';activeStatus.value=''}
}
function online(){if(!activeId.value)void load(true)}
onMounted(()=>{void load(true);window.addEventListener('online',online)})
onUnmounted(()=>window.removeEventListener('online',online))
watch(()=>uploader.lastCompleted,async completion=>{
  if(!completion||!('batchId' in completion)||completion.batchId!==props.batchId)return
  await load()
  emit('changed')
})
usePolling(async()=>{if((items.value.length||manifest.value?.state==='waiting')&&!activeId.value)await load()},12000)
</script>

<template>
<section v-if="loading||items.length||manifest?.state==='waiting'||error" class="panel stack" aria-label="Незавершённые загрузки" style="margin-bottom:19px">
  <div class="panel-header">
    <div>
      <h2>Незавершённые загрузки</h2>
      <p class="meta" style="margin:6px 0 0">Не затрагиваем готовые фотографии партии.</p>
    </div>
    <UiButton small :disabled="!!activeId" @click="load(true)">Проверить</UiButton>
  </div>
  <div v-if="loading" class="meta">Проверяем незавершённые файлы…</div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <div v-if="manifest?.state==='waiting'" class="alert warning">
    Партия ещё не полная: сервер сохранил {{manifest.finalized}} из {{manifest.expected}} ожидаемых фотографий.
    <template v-if="manifest.missing">Не начиналась передача {{manifest.missing}} файлов.</template>
    Выберите ту же папку в загрузчике ФО для продолжения.
    <div v-for="item in manifest.files.filter(file=>file.state==='not_started'||file.state==='missing_saved').slice(0,10)" :key="item.upload_id" class="meta" style="margin-top:5px;overflow-wrap:anywhere">
      {{item.relative_path}} · {{item.state==='missing_saved'?'оригинал отсутствует на сервере':'ещё не передан'}}
    </div>
    <div v-if="manifest.files.filter(file=>file.state==='not_started'||file.state==='missing_saved').length>10" class="meta">И другие отсутствующие фотографии…</div>
  </div>
  <div v-if="items.length" class="alert warning">
    {{items.length}} файлов ещё не завершены. Пока они есть, обработка партии недоступна.
    Полностью загруженные файлы автоматически проходят проверку и сохранение.
  </div>
  <div v-for="item in items" :key="item.id" class="stack-sm"
    style="padding:12px 0;border-bottom:1px solid var(--border-subtle)">
    <div class="row between wrap">
      <div style="min-width:0;flex:1">
        <strong style="overflow-wrap:anywhere">{{item.filename}}</strong>
        <div class="meta">
          {{bytes(item.received)}} / {{bytes(item.size)}} ·
          {{batchUploading?'идёт загрузка партии':!item.has_part?'временный файл на сервере отсутствует':item.can_finalize?'всё передано, осталось сохранить':'передача прервана'}}
        </div>
      </div>
      <div class="row wrap">
        <UiButton v-if="batchUploading&&(!job.recovery||job.recovery.item.id===item.id)" small @click="uploader.show('fo')">Открыть загрузку</UiButton>
        <template v-else-if="!activeId&&!batchUploading">
          <UiButton v-if="item.can_finalize" small :disabled="disabled" @click="finish(item)">Завершить</UiButton>
          <UiButton v-else-if="item.has_part" small :disabled="disabled" @click="pick(item)">Продолжить</UiButton>
          <UiButton small kind="danger" :disabled="disabled" @click="confirmCancel=item">Отменить</UiButton>
        </template>
      </div>
    </div>
    <input :id="'pending-source-'+item.id" type="file"
      style="display:none" :disabled="!!activeId||disabled" @change="continueFile(item,$event)"/>
    <div v-if="activeId===item.id" class="meta">{{activeStatus}}</div>
    <div v-if="errors[item.id]" class="alert error" role="alert">{{errors[item.id]}}</div>
  </div>
  <div v-if="items.some(item=>!item.can_finalize&&item.has_part)" class="meta">
    После обновления страницы браузер не имеет доступа к старым файлам.
    Для продолжения выберите тот же оригинал — мы сверим уже переданную часть по SHA-256.
  </div>
  <ConfirmDialog v-if="confirmCancel" title="Отменить незавершённую передачу?"
    :message="'Будет удалена только незавершённая копия «'+confirmCancel.filename+'». Готовые фотографии останутся без изменений.'"
    confirm-label="Отменить передачу" :danger="true" :busy="!!activeId"
    @confirm="cancel" @cancel="confirmCancel=null"/>
</section>
</template>
