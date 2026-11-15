<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {libraryNoticesApi,type LibraryStatus} from '../../api/libraryNotices'
import UploadPanel from '../../features/fo/UploadPanel.vue'
import ReferenceUpdateNotice from '../../features/fo/ReferenceUpdateNotice.vue'
import UploadDialog from './UploadDialog.vue'

const upload=useUploadCenterStore()
const props=defineProps<{target?:{id:string;name:string}}>()
const library=ref<LibraryStatus|null>(null),noticeError=ref('')
onMounted(async()=>{
  if(props.target)return
  try{library.value=await libraryNoticesApi.status()}
  catch{noticeError.value='Не удалось проверить обновления образцов'}
})
</script>

<template>
  <UploadDialog :title="target?'Продолжить загрузку ФО':'Загрузить фотографии'" heading-id="fo-upload-heading" @close="upload.closeForm()">
    <ReferenceUpdateNotice v-if="library?.notice" :status="library" @ack="library=$event"/>
    <div v-if="noticeError" class="alert warning">{{noticeError}}</div>
    <UploadPanel :target="target"/>
  </UploadDialog>
</template>
