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
import {useNoticeStore} from '../../stores/notice'
import UiButton from '../../components/ui/UiButton.vue'
const emit=defineEmits<{
  (e:'finished',batchId:string):void
  (e:'state',busy:boolean,percent:number,phase:string):void
}>()
const entries=ref<UploadEntry[]>([]),folder=ref(''),batchId=ref(''),running=ref(false),error=ref(''),finished=ref(0)
const amounts=ref<number[]>([]),phase=ref('')
const autoProcess=ref(false),autoThreshold=ref(.50),manifestRegistered=ref(false)
let controller:AbortController|null=null
const total=computed(()=>entries.value.reduce((s,e)=>s+e.file.size,0))
const uploaded=computed(()=>amounts.value.reduce((a,b)=>a+b,0))
const percent=computed(()=>total.value?Math.min(100,100*uploaded.value/total.value):0)
watch([running,percent,phase],()=>emit('state',running.value,percent.value,phase.value),{immediate:true})
const notice=useNoticeStore(),uploadSettings=useUploadSettingsStore()
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
  if(!files)return
  try{
    const batch=directoryEntries(files)
    entries.value=batch.entries;folder.value=batch.folder;batchId.value='';amounts.value=entries.value.map(()=>0)
    manifestRegistered.value=false
    error.value='';finished.value=0;phase.value=''
  }catch(err){error.value=errorText(err)}
}
function storageKey(){
  return 'ps.folder:'+folder.value+':'+entries.value.length+':'+total.value
}
function storedId(){try{return localStorage.getItem(storageKey())}catch{return null}}
function saveId(id:string){try{localStorage.setItem(storageKey(),id)}catch{}}
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
    phase.value='Проверка состава папки…'
    let manifestIds:string[]|null=null
    const current=await request(()=>batchApi.manifest(batchId.value))
    if(current.state!=='legacy'){
      if(!matches(current))throw new Error('Выбранная папка не совпадает с манифестом партии. Создайте новую партию.')
      manifestRegistered.value=true
      autoProcess.value=current.auto_process_state==='waiting'||current.auto_process_state==='queued'
      autoThreshold.value=current.auto_process_threshold??.50
      const ids=new Map(current.files.map(file=>[file.relative_path,file.upload_id]))
      manifestIds=entries.value.map(e=>ids.get(e.relative)!)
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
    const failures=await runUploadQueue(entries.value.length,uploadSettings.parallelUploads,signal,async idx=>{
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
      finished.value++;amounts.value[idx]=entry.file.size
    },{
      haltAfterFailuresWithoutSuccess:Math.min(3,uploadSettings.parallelUploads),
      onFailure:failure=>{
        if(error.value)return
        const file=entries.value[failure.index]?.file.name||'Неизвестный файл'
        const code=failure.error instanceof ApiError&&failure.error.status
          ?'HTTP '+failure.error.status+' · ':''
        error.value='Ошибка «'+file+'»: '+code+errorText(failure.error)
      }
    })
    if(failures.length){
      const last=manifestIds?await request(()=>batchApi.manifest(batchId.value)):null
      if(last?.state!=='complete'){
        const details=failures.slice(0,3).map(({index,error})=>
          entries.value[index]?.file.name+': '+errorText(error)).join('; ')
        throw new Error('Не загружено '+failures.length+' из '+entries.value.length+' файлов: '+details)
      }
    }
    if(manifestIds){
      phase.value='Проверка полноты партии…'
      const confirmed=await request(()=>batchApi.manifest(batchId.value))
      if(confirmed.state!=='complete')
        throw new Error('Сервер ожидает ещё '+confirmed.pending+' файлов. Выберите эту папку для продолжения.')
    }
    notice.add(autoProcess.value
      ?'Все ФО сохранены. MegaLoc автоматически встанет в очередь; миниатюры формируются отдельно.'
      :'Все фотографии партии сохранены. Миниатюры формируются отдельно.','ok')
    emit('finished',batchId.value)
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
  <div v-if="entries.length" class="stack-sm" style="border-top:1px solid var(--border-subtle);padding-top:12px">
    <label class="row wrap" style="gap:10px;align-items:center">
      <input type="checkbox" v-model="autoProcess" :disabled="running||manifestRegistered" aria-label="Автоматически обработать MegaLoc после загрузки"/>
      <strong>Автоматически обработать MegaLoc после загрузки</strong>
    </label>
    <div class="meta">После проверки всех файлов задание создаётся на сервере даже при закрытом браузере. Автозапуск можно отменить до постановки в очередь.</div>
    <label v-if="autoProcess" class="field" style="max-width:270px">
      Порог группировки MegaLoc: {{autoThreshold.toFixed(2)}}
      <input type="range" v-model.number="autoThreshold" min=".50" max=".99" step=".01" :disabled="running||manifestRegistered" aria-label="Порог MegaLoc для автоматической обработки"/>
    </label>
    <div v-if="manifestRegistered" class="meta">Настройки этой партии уже сохранены на сервере и не меняются при повторном выборе папки.</div>
  </div>
  <div v-if="running||uploaded" class="stack-sm">
    <div class="row between meta"><span>Передано {{bytes(uploaded)}} / {{bytes(total)}}</span><span>{{percent.toFixed(1)}}%</span></div>
    <div class="progress-track" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100"><span class="progress-fill" :style="{width:percent+'%'}"/></div>
    <div class="meta" role="status">{{phase}} · {{finished}} из {{entries.length}} файлов · до {{uploadSettings.parallelUploads}} передач одновременно</div>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
</section>
</template>
