<script setup lang="ts">
import {onMounted,onUnmounted} from 'vue'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {uploadKindLabel,uploadPercent,uploadStatusLabel} from '../../utils/transferPresentation'
import FoUploadDialog from './FoUploadDialog.vue'
import ReferenceUploadDialog from './ReferenceUploadDialog.vue'
import UploadQueueDialog from './UploadQueueDialog.vue'

const upload=useUploadCenterStore()
function key(event:KeyboardEvent){
  if(event.defaultPrevented||event.key!=='Escape')return
  if(upload.queueOpen)upload.closeQueue()
  else if(upload.form)upload.closeForm()
}
onMounted(()=>document.addEventListener('keydown',key))
onUnmounted(()=>{
  document.removeEventListener('keydown',key)
  upload.reset()
})
</script>
<template>
  <div v-if="upload.current&&!upload.queueOpen" class="upload-floating-stack">
    <button type="button" class="upload-floating" @click="upload.showQueue()">
      <span class="upload-floating-dot" :class="{active:upload.current.status==='running'}" aria-hidden="true"/>
      <span class="upload-floating-name">{{uploadKindLabel(upload.current.kind)}} · {{upload.current.name}}</span>
      <strong>{{upload.current.status==='running'?uploadPercent(upload.current)+'%':uploadStatusLabel(upload.current.status)}}</strong>
    </button>
  </div>
  <FoUploadDialog v-if="upload.form?.mode==='fo'" :key="upload.form.id"/>
  <ReferenceUploadDialog v-else-if="upload.form" :key="upload.form.id"
    :mode="upload.form.mode" :sam="upload.form.sam" :sam-label="upload.form.samLabel"/>
  <UploadQueueDialog v-if="upload.queueOpen"/>
</template>
