<script setup lang="ts">
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {useNoticeStore} from '../../stores/notice'
import CreateConstructionDialog from '../../features/references/CreateConstructionDialog.vue'
import ReferenceUploader from '../../features/references/ReferenceUploader.vue'
import UploadDialog from './UploadDialog.vue'

defineProps<{mode:'construction'|'single';sam:string;samLabel:string}>()
const upload=useUploadCenterStore(),notice=useNoticeStore()
function noChanges(message:string){
  upload.closeForm()
  notice.add(message,'info')
}
function created(sam:string){
  upload.closeForm()
  upload.complete({sam})
  notice.add('Конструкция создана. Теперь можно добавить образцы.','ok')
}
</script>

<template>
  <UploadDialog :title="mode==='construction'?'Создать конструкцию':'Добавить фото'"
    heading-id="reference-upload-heading" @close="upload.closeForm()">
    <CreateConstructionDialog v-if="mode==='construction'"
      @dismiss="upload.closeForm()" @created="created" @no-changes="noChanges"/>
    <ReferenceUploader v-else :selected-sam="sam" :selected-label="samLabel" @no-changes="noChanges"/>
  </UploadDialog>
</template>
