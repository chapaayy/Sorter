<script setup lang="ts">
import {onMounted,onUnmounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import type {PendingUpload} from '../../types/api'
import {resumePendingUpload} from '../../utils/upload'
import {bytes,errorText} from '../../utils/format'
import {usePolling} from '../../composables/usePolling'
import UiButton from '../../components/ui/UiButton.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'

const props=defineProps<{batchId:string;disabled?:boolean}>()
const emit=defineEmits<{(e:'changed'):void}>()
const items=ref<PendingUpload[]>([]),loading=ref(true),error=ref('')
const activeId=ref(''),activeStatus=ref(''),confirmCancel=ref<PendingUpload|null>(null)
const errors=ref<Record<string,string>>({})
const progress=ref<Record<string,number>>({})
let controller:AbortController|null=null

async function load(autoFinish=false){
  if(activeId.value)return
  try{
    const result=await batchApi.pending(props.batchId)
    items.value=result.uploads
    error.value=''
    if(autoFinish&&!props.disabled){
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
  if(activeId.value||props.disabled)return
  activeId.value=item.id;activeStatus.value='Проверка и сохранение файла…'
  try{
    await batchApi.finishPending(item.id)
    delete errors.value[item.id]
    await batchApi.pending(props.batchId).then(result=>{items.value=result.uploads})
    emit('changed')
  }catch(err){
    errors.value[item.id]=(automatic?'Автозавершение: ':'')+errorText(err)
  }finally{activeId.value='';activeStatus.value=''}
}
function pick(item:PendingUpload){
  document.getElementById('pending-source-'+item.id)?.click()
}
async function continueFile(item:PendingUpload,event:Event){
  const input=event.target as HTMLInputElement
  const file=input.files?.item(0)
  input.value=''
  if(!file||activeId.value||props.disabled)return
  activeId.value=item.id;activeStatus.value='Проверяем оригинал…'
  delete errors.value[item.id]
  controller=new AbortController()
  try{
    await resumePendingUpload(item.id,{kind:'fo',batchId:props.batchId},
      {file,relative:file.name},item,controller.signal,
      count=>{progress.value[item.id]=count},
      state=>{activeStatus.value=state.state==='waiting'
        ?'Ожидание соединения · повтор через '+Math.ceil((state.delayMs||1000)/1000)+' с'
        :'Передача восстановлена'})
    delete errors.value[item.id]
    await batchApi.pending(props.batchId).then(result=>{items.value=result.uploads})
    emit('changed')
  }catch(err){
    errors.value[item.id]=controller.signal.aborted?'Передача приостановлена. Можно продолжить позже.':errorText(err)
  }finally{controller=null;activeId.value='';activeStatus.value=''}
}
async function cancel(){
  const item=confirmCancel.value
  if(!item||activeId.value||props.disabled)return
  activeId.value=item.id;activeStatus.value='Отменяем незавершённую передачу…'
  try{
    await batchApi.cancelPending(item.id)
    confirmCancel.value=null
    delete errors.value[item.id]
    await batchApi.pending(props.batchId).then(result=>{items.value=result.uploads})
    emit('changed')
  }catch(err){errors.value[item.id]=errorText(err)}
  finally{activeId.value='';activeStatus.value=''}
}
function online(){if(!activeId.value)void load(true)}
onMounted(()=>{void load(true);window.addEventListener('online',online)})
onUnmounted(()=>{controller?.abort();window.removeEventListener('online',online)})
usePolling(async()=>{if(items.value.length&&!activeId.value)await load()},12000)
</script>

<template>
<section v-if="loading||items.length||error" class="panel stack" aria-label="Незавершённые загрузки" style="margin-bottom:19px">
  <div class="panel-header">
    <div>
      <h2>Незавершённые загрузки</h2>
      <p class="meta" style="margin:6px 0 0">Не затрагиваем готовые фотографии партии.</p>
    </div>
    <UiButton small :disabled="!!activeId" @click="load(true)">Проверить</UiButton>
  </div>
  <div v-if="loading" class="meta">Проверяем незавершённые файлы…</div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
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
          {{bytes(progress[item.id]??item.received)}} / {{bytes(item.size)}} ·
          {{!item.has_part?'временный файл на сервере отсутствует':item.can_finalize?'всё передано, осталось сохранить':'передача прервана'}}
        </div>
      </div>
      <div class="row wrap">
        <UiButton v-if="activeId===item.id&&controller" small kind="danger" @click="controller.abort()">Пауза</UiButton>
        <template v-else-if="!activeId">
          <UiButton v-if="item.can_finalize" small :disabled="disabled" @click="finish(item)">Завершить</UiButton>
          <UiButton v-else-if="item.has_part" small :disabled="disabled" @click="pick(item)">Продолжить</UiButton>
          <UiButton small kind="danger" :disabled="disabled" @click="confirmCancel=item">Отменить</UiButton>
        </template>
      </div>
    </div>
    <input :id="'pending-source-'+item.id" type="file" accept=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff"
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
