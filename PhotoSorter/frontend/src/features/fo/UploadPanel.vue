<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {runApi} from '../../api/runs'
import {directoryEntries} from '../../utils/upload'
import type {UploadEntry} from '../../utils/upload'
import {readFolderBatch} from '../../utils/foTransfer'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {bytes,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'

const upload=useUploadCenterStore()
const entries=ref<UploadEntry[]>([]),folder=ref(''),error=ref('')
const source=ref<File[]>([]),unknown=ref(0),includeUnknown=ref(false)
const autoProcess=ref(false),autoThreshold=ref(.50)
const chosenAuto=ref(false)
const total=computed(()=>entries.value.reduce((sum,e)=>sum+e.file.size,0))
const resumable=computed(()=>!!entries.value.length&&!!readFolderBatch({name:folder.value,entries:entries.value}))
onMounted(async()=>{
  try{
    const defaults=await runApi.autoSettings()
    if(!chosenAuto.value)autoProcess.value=defaults.auto_process_new_batches
    autoThreshold.value=defaults.grouping_threshold
  }catch{/* Safe defaults */}
})
function choose(e:Event){
  const input=e.target as HTMLInputElement
  source.value=Array.from(input.files||[])
  input.value=''
  unknown.value=0
  includeUnknown.value=false
  applySelection()
}
function applySelection(){
  if(!source.value.length){entries.value=[];return}
  try{
    const batch=directoryEntries(source.value,includeUnknown.value)
    unknown.value=batch.unknown
    entries.value=batch.entries;folder.value=batch.folder
    error.value=''
  }catch(err){entries.value=[];error.value=errorText(err)}
}
watch(includeUnknown,applySelection)
function submit(){
  if(!entries.value.length)return
  upload.enqueue({kind:'fo',name:folder.value,entries:[...entries.value],
    autoProcess:autoProcess.value,threshold:autoThreshold.value})
}
</script>
<template>
<section class="panel stack" aria-label="Загрузка фотографий">
  <label class="upload-drop">
    <input type="file" multiple webkitdirectory directory @change="choose"/>
    <span style="font-size:27px;color:var(--muted)">▤</span><br/>
    <strong>Выбрать папку с фото и видео</strong>
    <p class="meta" style="margin:6px 0 0">Оригиналы сохраняются без конвертации · до 2 ГиБ на файл</p>
  </label>
  <label v-if="unknown" class="row wrap">
    <input v-model="includeUnknown" type="checkbox" />
    <span>Проверить на сервере файлы с неопознанным форматом ({{unknown}})</span>
  </label>
  <div v-if="entries.length" class="row wrap between">
    <div>
      <strong>{{folder}}</strong>
      <p class="meta" style="margin:3px 0">{{entries.length.toLocaleString('ru-RU')}} файлов · {{bytes(total)}}</p>
    </div>
    <UiButton kind="primary" @click="submit">{{resumable?'Продолжить':'Загрузить'}}</UiButton>
  </div>
  <label v-if="entries.length" class="row wrap" style="gap:10px;align-items:center">
    <input v-model="autoProcess" type="checkbox" @change="chosenAuto=true"
      aria-label="Обработать после загрузки"/>
    <span>Обработать поддерживаемые фото после загрузки</span>
  </label>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
</section>
</template>
