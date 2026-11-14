<script setup lang="ts">
import {onMounted,onUnmounted} from 'vue'
import {useUploadCenterStore,type UploadChannel} from '../../stores/uploadCenter'
import FoUploadDialog from './FoUploadDialog.vue'
import ReferenceUploadDialog from './ReferenceUploadDialog.vue'

const upload=useUploadCenterStore()
const channels=[{id:'fo',label:'Загрузка ФО'},{id:'references',label:'Загрузка образцов'}] as const
function label(id:UploadChannel,text:string){
  return upload.windows[id].mode==='construction'?'Создание конструкции':text
}
function key(event:KeyboardEvent){
  if(event.defaultPrevented||event.key!=='Escape')return
  for(const {id} of channels)if(upload.windows[id].visible)upload.close(id)
}
onMounted(()=>document.addEventListener('keydown',key))
onUnmounted(()=>{
  document.removeEventListener('keydown',key)
  for(const {id} of channels)upload.finish(id)
})
</script>
<template>
  <div v-if="channels.some(({id})=>upload.windows[id].mounted&&!upload.windows[id].visible)" class="upload-floating-stack">
    <template v-for="{id,label:text} in channels" :key="id">
      <button v-if="upload.windows[id].mounted&&!upload.windows[id].visible" class="upload-floating"
        type="button" @click="upload.show(id)">
        <span class="upload-floating-dot" :class="{active:upload.windows[id].busy}"/>
        {{label(id,text)}}
        <span v-if="upload.windows[id].busy&&upload.windows[id].mode!=='construction'"
          :title="upload.windows[id].label">{{Math.round(upload.windows[id].progress)}}%</span>
        <span v-else-if="!upload.windows[id].busy">Продолжить</span>
      </button>
    </template>
  </div>
  <FoUploadDialog v-if="upload.windows.fo.mounted"/>
  <ReferenceUploadDialog v-if="upload.windows.references.mounted"/>
</template>
