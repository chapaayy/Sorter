<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {resumePendingUpload} from '../../utils/upload'
import {bytes,errorText} from '../../utils/format'
import type {RecoverySource} from '../../stores/uploadCenter'
import UiButton from '../../components/ui/UiButton.vue'

const props=defineProps<{source:RecoverySource}>()
const emit=defineEmits<{
  (e:'finished',batchId:string,message:string):void
  (e:'state',busy:boolean,percent:number,phase:string):void
}>()
const running=ref(true),sent=ref(props.source.item.received),phase=ref('Проверяем оригинал…'),error=ref('')
const percent=computed(()=>100*sent.value/props.source.item.size)
let controller:AbortController|null=null
watch([running,percent,phase],()=>emit('state',running.value,percent.value,phase.value),{immediate:true})

async function start(){
  if(controller)return
  const {batchId,item,file}=props.source
  controller=new AbortController()
  const signal=controller.signal
  running.value=true;phase.value='Проверяем оригинал…';error.value=''
  try{
    await resumePendingUpload(item.id,{kind:'fo',batchId},{file,relative:file.name},item,signal,
      count=>{sent.value=count},
      state=>{phase.value=state.state==='waiting'
        ?'Ожидание соединения · повтор через '+Math.ceil((state.delayMs||1000)/1000)+' с'
        :'Передача файлов'})
    emit('finished',batchId,'Загрузка фото завершена: '+item.filename)
  }catch(err){
    error.value=signal.aborted?'Передача приостановлена. Можно продолжить позже.':errorText(err)
  }finally{controller=null;running.value=false;phase.value=''}
}
function pause(){controller?.abort()}
onMounted(start)
onUnmounted(pause)
</script>
<template>
  <div class="stack">
    <strong style="overflow-wrap:anywhere">{{source.item.filename}}</strong>
    <div class="row between wrap">
      <span class="meta">{{bytes(sent)}} / {{bytes(source.item.size)}}</span>
      <UiButton v-if="running" kind="danger" @click="pause">Пауза</UiButton>
      <UiButton v-else kind="primary" @click="start">Продолжить</UiButton>
    </div>
    <div class="progress-track" role="progressbar" aria-label="Докачка фото" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(percent)">
      <span class="progress-fill" :style="{width:percent+'%'}"/>
    </div>
    <div v-if="phase" class="meta" role="status">{{phase}}</div>
    <div v-if="error" class="alert error" role="alert">{{error}}</div>
  </div>
</template>
