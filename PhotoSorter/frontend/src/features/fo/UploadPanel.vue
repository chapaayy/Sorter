<script setup lang="ts">
import {computed,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {canResumeUpload} from '../../utils/batches'
import {directoryEntries,uploadOne} from '../../utils/upload'
import type {UploadEntry} from '../../utils/upload'
import {bytes,errorText} from '../../utils/format'
import {useNoticeStore} from '../../stores/notice'
import UiButton from '../../components/ui/UiButton.vue'
const emit=defineEmits<{(e:'finished',batchId:string):void}>()
const entries=ref<UploadEntry[]>([]),folder=ref(''),batchId=ref(''),running=ref(false),error=ref(''),finished=ref(0)
const amounts=ref<number[]>([])
let controller:AbortController|null=null
const total=computed(()=>entries.value.reduce((s,e)=>s+e.file.size,0))
const uploaded=computed(()=>amounts.value.reduce((a,b)=>a+b,0))
const percent=computed(()=>total.value?Math.min(100,100*uploaded.value/total.value):0)
const notice=useNoticeStore()
function choose(e:Event){
  const files=(e.target as HTMLInputElement).files
  if(!files)return
  try{
    const batch=directoryEntries(files)
    entries.value=batch.entries;folder.value=batch.folder;batchId.value='';amounts.value=entries.value.map(()=>0)
    error.value='';finished.value=0
  }catch(err){error.value=errorText(err)}
}
function storageKey(){
  return 'ps.folder:'+folder.value+':'+entries.value.length+':'+total.value
}
function storedId(){try{return localStorage.getItem(storageKey())}catch{return null}}
function saveId(id:string){try{localStorage.setItem(storageKey(),id)}catch{}}
async function start(){
  if(!entries.value.length||running.value)return
  error.value='';running.value=true;controller=new AbortController()
  try{
    const saved=storedId()
    if(saved){
      const old=await batchApi.one(saved).catch(()=>null)
      if(old && canResumeUpload(old))batchId.value=saved
    }
    if(!batchId.value){const created=await batchApi.create(folder.value);batchId.value=created.batch_id;saveId(batchId.value)}
    const signal=controller.signal,queue=entries.value.map((_,i)=>i)
    let done=0
    async function worker(){
      while(queue.length){
        if(signal.aborted)throw new DOMException('Пауза','AbortError')
        const idx=queue.shift()
        if(idx===undefined)break
        const entry=entries.value[idx]
        if(!entry)continue
        await uploadOne({kind:'fo',batchId:batchId.value},entry,signal,n=>{
          amounts.value[idx]=n
        })
        done++;finished.value=done;amounts.value[idx]=entry.file.size
      }
    }
    await Promise.all(Array.from({length:Math.min(3,queue.length)},worker))
    notice.add('Папка загружена. Миниатюры формируются отдельно.','ok')
    emit('finished',batchId.value)
  }catch(err){
    error.value=controller.signal.aborted?'Загрузка приостановлена. Выберите эту же папку и продолжите позже.':errorText(err)
  }finally{running.value=false;controller=null}
}
function stop(){controller?.abort()}
</script>
<template>
<section class="panel stack" aria-label="Загрузка папки ФО">
  <div class="panel-header"><h2>Новая партия фотографий</h2><span class="status">Загрузка с докачкой</span></div>
  <label class="upload-drop">
    <input type="file" multiple webkitdirectory directory :disabled="running" @change="choose"/>
    <span style="font-size:28px;color:var(--accent)">▤</span><br/>
    <strong>Выбрать папку ФО</strong>
    <p class="meta" style="margin:6px 0 0">JPEG, PNG, WebP, TIFF, BMP · до 60 МБ на файл</p>
  </label>
  <div v-if="entries.length" class="row wrap between">
    <div><strong>{{folder}}</strong><p class="meta" style="margin:3px 0">{{entries.length.toLocaleString('ru-RU')}} файлов · {{bytes(total)}}</p></div>
    <div class="row"><UiButton v-if="running" kind="danger" @click="stop">Пауза</UiButton><UiButton v-else kind="primary" @click="start">{{finished===entries.length?'Проверить повторно':'Начать / продолжить'}}</UiButton></div>
  </div>
  <div v-if="running||uploaded" class="stack-sm">
    <div class="row between meta"><span>Передано {{bytes(uploaded)}} / {{bytes(total)}}</span><span>{{percent.toFixed(1)}}%</span></div>
    <div class="progress-track" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100"><span class="progress-fill" :style="{width:percent+'%'}"/></div>
    <div class="meta">{{finished}} из {{entries.length}} файлов · до 3 передач одновременно</div>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
</section>
</template>
