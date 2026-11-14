<script setup lang="ts">
import {computed,ref,watch,nextTick,onMounted,onUnmounted} from 'vue'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {useNoticeStore} from '../../stores/notice'
import {libraryNoticesApi} from '../../api/libraryNotices'
import type {LibraryStatus} from '../../api/libraryNotices'
import UploadPanel from '../../features/fo/UploadPanel.vue'
import RecoveryUpload from '../../features/fo/RecoveryUpload.vue'
import CreateConstructionDialog from '../../features/references/CreateConstructionDialog.vue'
import ReferenceUploader from '../../features/references/ReferenceUploader.vue'
import ReferenceUpdateNotice from '../../features/fo/ReferenceUpdateNotice.vue'

const upload=useUploadCenterStore(),notice=useNoticeStore()
const library=ref<LibraryStatus|null>(null),noticeError=ref('')
const closeButton=ref<HTMLButtonElement|null>(null)
const floating=ref<HTMLButtonElement|null>(null)
const heading=computed(()=>({fo:'Загрузить фотографии',construction:'Создать конструкцию',
  single:'Загрузить образцы',recovery:'Продолжить загрузку'}[upload.mode]))
const label=computed(()=>upload.mode==='fo'||upload.mode==='recovery'?'Загрузка ФО':'Загрузка образцов')
watch(()=>[upload.visible,upload.mode] as const,async([visible,mode])=>{
  if(!visible||mode!=='fo')return
  try{
    library.value=await libraryNoticesApi.status()
    noticeError.value=''
  }catch{noticeError.value='Не удалось проверить обновления образцов'}
},{immediate:true})
function onState(running:boolean,percent:number,phase:string){
  upload.report(running,percent,phase)
}
function collapse(){upload.close();void nextTick(()=>floating.value?.focus())}
function key(event:KeyboardEvent){if(!event.defaultPrevented&&event.key==='Escape'&&upload.visible)collapse()}
onMounted(()=>document.addEventListener('keydown',key))
onUnmounted(()=>{document.removeEventListener('keydown',key);upload.finish()})
watch(()=>upload.visible,shown=>{if(shown)void nextTick(()=>closeButton.value?.focus())})
function finishedFo(batchId:string,message:string){
  upload.finish({batchId})
  notice.add(message,'ok',{to:'/fo/'+batchId,label:'Открыть'})
}
function finishedRefs(message:string){
  upload.finish({})
  notice.add(message,'ok',{to:'/queue',label:'К очереди'})
}
function constructionCreated(sam:string){
  upload.finish({sam})
  notice.add('Конструкция создана. Теперь можно добавить образцы.','ok')
}
</script>
<template>
  <button v-if="upload.mounted&&!upload.visible" ref="floating" class="upload-floating"
    type="button" @click="upload.visible=true">
    <span class="upload-floating-dot" :class="{active:upload.busy}"/>
    {{label}}
    <span v-if="upload.busy" :title="upload.label">{{Math.round(upload.progress)}}%</span>
    <span v-else>Продолжить</span>
  </button>
  <Teleport to="body">
    <div v-if="upload.mounted" v-show="upload.visible" class="modal-overlay upload-overlay"
      @click.self="collapse">
      <section class="modal upload-modal" role="dialog" aria-modal="true"
        aria-labelledby="upload-modal-heading">
        <div class="row between upload-modal-header">
          <div>
            <h2 id="upload-modal-heading" style="margin-bottom:2px">
              {{heading}}
            </h2>

          </div>
          <button ref="closeButton" type="button" class="btn ghost icon" aria-label="Свернуть загрузку"
            @click="collapse">✕</button>
        </div>
        <ReferenceUpdateNotice v-if="upload.mode==='fo'&&library?.notice"
          :status="library" @ack="library=$event"/>
        <div v-if="noticeError&&upload.mode==='fo'" class="alert warning">{{noticeError}}</div>
        <UploadPanel v-if="upload.mode==='fo'" :key="upload.session" @finished="finishedFo"
          @batch="upload.batchId=$event" @state="onState"/>
        <CreateConstructionDialog v-else-if="upload.mode==='construction'" :key="upload.session"
          @dismiss="upload.finish()" @created="constructionCreated" @finished="finishedRefs" @state="onState"/>
        <RecoveryUpload v-else-if="upload.mode==='recovery'&&upload.recovery" :key="upload.session"
          :source="upload.recovery" @finished="finishedFo" @state="onState"/>
        <ReferenceUploader v-else-if="upload.mode==='single'" :key="upload.session"
          :selected-sam="upload.sam" :selected-label="upload.samLabel"
          @finished="finishedRefs"
          @state="onState"/>
        <div class="row between upload-modal-footer">
          <span class="meta">{{upload.busy?'Загрузка продолжается даже после закрытия окна':''}}</span>
          <button type="button" class="btn" @click="collapse">
            {{upload.busy?'Свернуть':'Закрыть'}}
          </button>
        </div>
      </section>
    </div>
  </Teleport>
</template>
