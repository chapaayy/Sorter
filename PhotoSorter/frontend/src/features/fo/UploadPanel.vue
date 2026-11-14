<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,watch} from 'vue'
import {batchApi} from '../../api/batches'
import {runApi} from '../../api/runs'
import {ApiError} from '../../api/client'
import {canResumeUpload} from '../../utils/batches'
import {directoryEntries,uploadOne,expectedUploadId} from '../../utils/upload'
import {withUploadRetry} from '../../utils/uploadRetry'
import {runUploadQueue} from '../../utils/uploadQueue'
import {useUploadSettingsStore} from '../../stores/uploadSettings'
import type {UploadEntry} from '../../utils/upload'
import type {BatchUploadManifest,UploadManifestFile} from '../../types/api'
import {bytes,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
const emit=defineEmits<{
  (e:'finished',batchId:string,message:string):void
  (e:'batch',batchId:string):void
  (e:'state',busy:boolean,percent:number,phase:string):void
}>()
const entries=ref<UploadEntry[]>([]),folder=ref(''),batchId=ref(''),running=ref(false),error=ref('')
const source=ref<File[]>([]),unknown=ref(0),includeUnknown=ref(false)
const amounts=ref<number[]>([]),phase=ref('')
const completed=ref(new Set<number>())
const finished=computed(()=>completed.value.size)
const autoProcess=ref(false),autoThreshold=ref(.50),manifestRegistered=ref(false),hasSavedSession=ref(false)
let controller:AbortController|null=null
const total=computed(()=>entries.value.reduce((s,e)=>s+e.file.size,0))
const uploaded=computed(()=>amounts.value.reduce((a,b)=>a+b,0))
const resumable=computed(()=>!!entries.value.length&&hasSavedSession.value)
const percent=computed(()=>total.value?Math.min(100,100*uploaded.value/total.value):0)
watch([running,percent,phase],()=>emit('state',running.value,percent.value,phase.value),{immediate:true})
const uploadSettings=useUploadSettingsStore()
onMounted(async()=>{
  try{
    const defaults=await runApi.autoSettings()
    if(!manifestRegistered.value&&!running.value){
      autoProcess.value=defaults.auto_process_new_batches
      autoThreshold.value=defaults.grouping_threshold
    }
  }catch{ /* The safe default is never to auto-process without consent. */ }
})
function choose(e:Event){
  const files=(e.target as HTMLInputElement).files
  source.value=Array.from(files||[])
  unknown.value=0
  includeUnknown.value=false
  applySelection()
}
function applySelection(){
  if(!source.value.length){entries.value=[];return}
  try{
    const batch=directoryEntries(source.value,includeUnknown.value)
    unknown.value=batch.unknown
    entries.value=batch.entries;folder.value=batch.folder;batchId.value='';amounts.value=entries.value.map(()=>0)
    manifestRegistered.value=false
    error.value='';completed.value.clear();phase.value='';hasSavedSession.value=!!storedId()
  }catch(err){entries.value=[];error.value=errorText(err)}
}
watch(includeUnknown,applySelection)
function storageKey(){
  return 'ps.folder:'+folder.value+':'+entries.value.length+':'+total.value
}
function storedId(){try{return localStorage.getItem(storageKey())}catch{return null}}
function saveId(id:string){try{localStorage.setItem(storageKey(),id)}catch{};hasSavedSession.value=true}
async function start(){
  if(!entries.value.length||running.value)return
  error.value='';running.value=true;phase.value='Подготовка партии…';controller=new AbortController()
  try{
    const signal=controller.signal
    const request=<T,>(fn:()=>Promise<T>)=>withUploadRetry(fn,signal)
    const matches=(manifest:BatchUploadManifest)=>{
      if(manifest.files.length!==entries.value.length)return false
      const files=new Map(manifest.files.map(file=>[file.relative_path,file]))
      return entries.value.every(e=>{
        const match=files.get(e.relative)
        return match?.filename===e.file.name && match.size===e.file.size
      })
    }
    const saved=storedId()
    if(saved&&!batchId.value){
      const old=await request(()=>batchApi.one(saved)).catch(err=>{
        if(err instanceof ApiError&&err.status===404)return null
        throw err
      })
      if(old&&canResumeUpload(old)){
        if(old.upload_manifest_state){
          const previous=await request(()=>batchApi.manifest(saved))
          if(matches(previous))batchId.value=saved
        }else batchId.value=saved
      }
    }
    if(!batchId.value){
      const created=await batchApi.create(folder.value)
      batchId.value=created.batch_id;saveId(batchId.value)
    }
    emit('batch',batchId.value)
    phase.value='Проверка состава папки…'
    let manifestIds:string[]|null=null
    const current=await request(()=>batchApi.manifest(batchId.value))
    if(current.state!=='legacy'){
      if(!matches(current))throw new Error('Выбранная папка не совпадает с манифестом партии. Создайте новую партию.')
      manifestRegistered.value=true
      autoProcess.value=current.auto_process_state==='waiting'||current.auto_process_state==='queued'
      autoThreshold.value=current.auto_process_threshold??.50
      const byPath=new Map(current.files.map(file=>[file.relative_path,file]))
      const received=entries.value.map(entry=>byPath.get(entry.relative)!)
      manifestIds=received.map(file=>file.upload_id)
      completed.value=new Set(received.flatMap((file,index)=>file.state==='finalized'?[index]:[]))
      amounts.value=received.map(file=>file.state==='finalized'?file.size:
        file.state==='unfinished'?Math.max(0,Math.min(file.received,file.size)):0)
    }else{
      const batch=await request(()=>batchApi.one(batchId.value))
      if((batch.photos??0)===0&&(batch.pending??0)===0&&(batch.runs??0)===0){
        const target={kind:'fo' as const,batchId:batchId.value}
        const plan:UploadManifestFile[]=entries.value.map(e=>({
          upload_id:expectedUploadId(target,e),relative_path:e.relative,
          filename:e.file.name,size:e.file.size
        }))
        await request(()=>batchApi.registerManifest(batchId.value,plan,
          autoProcess.value,autoThreshold.value))
        manifestRegistered.value=true
        manifestIds=plan.map(e=>e.upload_id)
      }
      // Existing partially uploaded legacy batches remain on their old flow.
    }
    const reconnecting=new Set<number>()
    phase.value='Передача файлов'
    const pending=entries.value.map((_,index)=>index).filter(index=>current.state==='legacy'||!completed.value.has(index))
    const failures=await runUploadQueue(pending.length,uploadSettings.parallelUploads,signal,async position=>{
      const idx=pending[position]!
      const entry=entries.value[idx]
      if(!entry)return
      await uploadOne({kind:'fo',batchId:batchId.value},entry,signal,n=>{
        amounts.value[idx]=n
      },state=>{
        if(state.state==='waiting')reconnecting.add(idx)
        else reconnecting.delete(idx)
        phase.value=reconnecting.size
          ?'Ожидание соединения · '+reconnecting.size+' файлов восстанавливаются'
          :'Передача файлов'
      },manifestIds?.[idx])
      reconnecting.delete(idx)
      phase.value=reconnecting.size?'Ожидание соединения':'Передача файлов'
      completed.value.add(idx);amounts.value[idx]=entry.file.size
    },{
      haltAfterFailuresWithoutSuccess:Math.min(3,uploadSettings.parallelUploads),
      onFailure:failure=>{
        if(error.value)return
        const file=entries.value[pending[failure.index]!]?.file.name||'Неизвестный файл'
        const code=failure.error instanceof ApiError&&failure.error.status
          ?'HTTP '+failure.error.status+' · ':''
        error.value='Ошибка «'+file+'»: '+code+errorText(failure.error)
      }
    })
    if(failures.length){
      const last=manifestIds?await request(()=>batchApi.manifest(batchId.value)):null
      if(last?.state!=='complete'){
        const details=failures.slice(0,3).map(({index,error})=>
          entries.value[pending[index]!]?.file.name+': '+errorText(error)).join('; ')
        throw new Error('Не загружено '+failures.length+' из '+entries.value.length+' файлов: '+details)
      }
    }
    if(manifestIds){
      phase.value='Проверка полноты партии…'
      const confirmed=await request(()=>batchApi.manifest(batchId.value))
      if(confirmed.state!=='complete')
        throw new Error('Сервер ожидает ещё '+confirmed.pending+' файлов. Выберите эту папку для продолжения.')
    }
    emit('finished',batchId.value,autoProcess.value
      ?'Все файлы партии сохранены. Автообработка доступна для поддерживаемых фотографий.'
      :'Все файлы партии сохранены. Миниатюры создаются для поддерживаемых фото.')
  }catch(err){
    const firstError=error.value
    error.value=controller.signal.aborted
      ?'Загрузка приостановлена. Выберите эту же папку и продолжите позже.'
      :firstError?firstError+' · '+errorText(err):errorText(err)
  }finally{running.value=false;phase.value='';controller=null}
}
function stop(){controller?.abort()}
onUnmounted(stop)
</script>
<template>
<section class="panel stack" aria-label="Загрузка фотографий">
  <label class="upload-drop">
    <input type="file" multiple webkitdirectory directory :disabled="running" @change="choose"/>
    <span style="font-size:27px;color:var(--muted)">▤</span><br/>
    <strong>Выбрать папку с фото и видео</strong>
    <p class="meta" style="margin:6px 0 0">Оригиналы сохраняются без конвертации · до 2 ГиБ на файл</p>
  </label>
  <label v-if="unknown" class="row wrap">
    <input v-model="includeUnknown" type="checkbox" :disabled="running||!!batchId"/>
    <span>Проверить на сервере файлы с неопознанным форматом ({{unknown}})</span>
  </label>
  <div v-if="entries.length" class="row wrap between">
    <div>
      <strong>{{folder}}</strong>
      <p class="meta" style="margin:3px 0">{{entries.length.toLocaleString('ru-RU')}} файлов · {{bytes(total)}}</p>
    </div>
    <div class="row">
      <UiButton v-if="running" @click="stop">Приостановить</UiButton>
      <UiButton v-else kind="primary" @click="start">
        {{finished===entries.length?'Проверить':resumable?'Продолжить':'Загрузить'}}
      </UiButton>
    </div>
  </div>
  <label v-if="entries.length" class="row wrap" style="gap:10px;align-items:center">
    <input v-model="autoProcess" type="checkbox" :disabled="running||manifestRegistered"
      aria-label="Обработать после загрузки"/>
    <span>Обработать поддерживаемые фото после загрузки</span>
  </label>
  <div v-if="running||uploaded" class="stack-sm">
    <div class="row between meta">
      <span>{{running?(phase.includes('Ожидание')?'Ожидание соединения':'Загрузка файлов'):'Передано'}} · {{finished}} из {{entries.length}}</span>
      <strong>{{percent.toFixed(1)}}%</strong>
    </div>
    <div class="progress-track" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100">
      <span class="progress-fill" :style="{width:percent+'%'}"/>
    </div>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
</section>
</template>
