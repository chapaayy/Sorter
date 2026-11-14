<script setup lang="ts">
import {ref,watch} from 'vue'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {useNoticeStore} from '../../stores/notice'
import {libraryNoticesApi,type LibraryStatus} from '../../api/libraryNotices'
import UploadPanel from '../../features/fo/UploadPanel.vue'
import RecoveryUpload from '../../features/fo/RecoveryUpload.vue'
import ReferenceUpdateNotice from '../../features/fo/ReferenceUpdateNotice.vue'
import UploadDialog from './UploadDialog.vue'

const upload=useUploadCenterStore(),notice=useNoticeStore()
const job=upload.windows.fo
const library=ref<LibraryStatus|null>(null),noticeError=ref('')
watch(()=>[job.visible,job.mode,job.session] as const,async([visible,mode],_,onCleanup)=>{
  if(!visible||mode!=='fo')return
  let current=true
  onCleanup(()=>{current=false})
  try{
    const status=await libraryNoticesApi.status()
    if(current){library.value=status;noticeError.value=''}
  }catch{if(current)noticeError.value='Не удалось проверить обновления образцов'}
},{immediate:true})
function onState(running:boolean,percent:number,phase:string){upload.report('fo',running,percent,phase)}
function finished(batchId:string,message:string){
  upload.finish('fo',{batchId})
  notice.add(message,'ok',{to:'/fo/'+batchId,label:'Открыть'})
}
</script>

<template>
  <UploadDialog :title="job.mode==='recovery'?'Продолжить загрузку':'Загрузить фотографии'"
    heading-id="fo-upload-heading" :visible="job.visible" :busy="job.busy" @close="upload.close('fo')">
    <ReferenceUpdateNotice v-if="job.mode==='fo'&&library?.notice" :status="library" @ack="library=$event"/>
    <div v-if="job.mode==='fo'&&noticeError" class="alert warning">{{noticeError}}</div>
    <UploadPanel v-if="job.mode==='fo'" :key="job.session" @finished="finished"
      @batch="job.batchId=$event" @state="onState"/>
    <RecoveryUpload v-else-if="job.recovery" :key="job.session" :source="job.recovery"
      @finished="finished" @state="onState"/>
  </UploadDialog>
</template>
