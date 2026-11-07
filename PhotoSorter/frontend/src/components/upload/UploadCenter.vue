<script setup lang="ts">
import {ref,watch} from 'vue'
import {useRouter} from 'vue-router'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {libraryNoticesApi} from '../../api/libraryNotices'
import type {LibraryStatus} from '../../api/libraryNotices'
import UploadPanel from '../../features/fo/UploadPanel.vue'
import ReferenceUploader from '../../features/references/ReferenceUploader.vue'
import ReferenceUpdateNotice from '../../features/fo/ReferenceUpdateNotice.vue'

const upload=useUploadCenterStore(),router=useRouter()
const library=ref<LibraryStatus|null>(null),noticeError=ref('')
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
function key(event:KeyboardEvent){if(event.key==='Escape'&&upload.visible)upload.close()}
function finishedFo(batchId:string){
  upload.finish()
  void router.push('/fo/'+batchId)
}
function finishedRefs(){upload.finish()}
</script>
<template>
  <button v-if="upload.mounted&&!upload.visible" class="upload-floating"
    type="button" @click="upload.visible=true">
    <span class="upload-floating-dot" :class="{active:upload.busy}"/>
    {{upload.mode==='fo'?'Загрузка ФО':'Загрузка образцов'}}
    <span v-if="upload.busy">{{Math.round(upload.progress)}}%</span>
    <span v-else>Продолжить</span>
  </button>
  <Teleport to="body">
    <div v-if="upload.mounted" v-show="upload.visible" class="modal-overlay upload-overlay"
      @click.self="upload.close" @keydown="key">
      <section class="modal upload-modal" role="dialog" aria-modal="true"
        aria-labelledby="upload-modal-heading">
        <div class="row between upload-modal-header">
          <div>
            <h2 id="upload-modal-heading" style="margin-bottom:2px">
              {{upload.mode==='fo'?'Загрузить папку фотографий':'Загрузить образцы'}}
            </h2>
            <p class="meta" style="margin:0">Передача с возможностью продолжить после обрыва</p>
          </div>
          <button type="button" class="btn ghost icon" aria-label="Свернуть загрузку"
            @click="upload.close">✕</button>
        </div>
        <ReferenceUpdateNotice v-if="upload.mode==='fo'&&library?.notice"
          :status="library" @ack="library=$event"/>
        <div v-if="noticeError&&upload.mode==='fo'" class="alert warning">{{noticeError}}</div>
        <UploadPanel v-if="upload.mode==='fo'" @finished="finishedFo"
          @state="onState"/>
        <ReferenceUploader v-else :selected-sam="upload.sam" :selected-label="upload.samLabel"
          :initial-mode="upload.mode"
          @finished="finishedRefs"
          @state="onState"/>
        <div class="row between upload-modal-footer">
          <span class="meta">{{upload.busy?'Загрузка продолжается даже после закрытия окна':''}}</span>
          <button type="button" class="btn" @click="upload.close">
            {{upload.busy?'Свернуть':'Закрыть'}}
          </button>
        </div>
      </section>
    </div>
  </Teleport>
</template>
