<script setup lang="ts">
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {useNoticeStore} from '../../stores/notice'
import CreateConstructionDialog from '../../features/references/CreateConstructionDialog.vue'
import ReferenceUploader from '../../features/references/ReferenceUploader.vue'
import UploadDialog from './UploadDialog.vue'

const upload=useUploadCenterStore(),notice=useNoticeStore()
const job=upload.windows.references
function onState(running:boolean,percent:number,phase:string){upload.report('references',running,percent,phase)}
function finished(message:string){
  upload.finish('references',{})
  notice.add(message,'ok',{to:'/queue',label:'К очереди'})
}
function created(sam:string){
  upload.finish('references',{sam})
  notice.add('Конструкция создана. Теперь можно добавить образцы.','ok')
}
</script>

<template>
  <UploadDialog :title="job.mode==='construction'?'Создать конструкцию':'Загрузить образцы'"
    heading-id="reference-upload-heading" :visible="job.visible" :busy="job.busy" @close="upload.close('references')">
    <CreateConstructionDialog v-if="job.mode==='construction'" :key="job.session"
      @dismiss="upload.finish('references')" @created="created" @state="onState"/>
    <ReferenceUploader v-else :key="job.session" :selected-sam="job.sam" :selected-label="job.samLabel"
      :initial-mode="job.mode==='single'?'single':'library'" @finished="finished" @state="onState"/>
  </UploadDialog>
</template>
