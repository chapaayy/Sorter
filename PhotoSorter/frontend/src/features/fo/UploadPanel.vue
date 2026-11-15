<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {runApi} from '../../api/runs'
import {directoryEntries} from '../../utils/upload'
import type {UploadEntry} from '../../utils/upload'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {bytes,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'

const upload=useUploadCenterStore()
const props=defineProps<{target?:{id:string;name:string}}>()
const entries=ref<UploadEntry[]>([]),name=ref(''),error=ref('')
const source=ref<File[]>([]),unknown=ref(0),includeUnknown=ref(false)
const autoProcess=ref(false),autoThreshold=ref(.50)
const chosenAuto=ref(false)
const total=computed(()=>entries.value.reduce((sum,e)=>sum+e.file.size,0))
const validName=computed(()=>!!name.value.trim()&&Array.from(name.value.trim()).length<=120)
onMounted(async()=>{
  if(props.target)return
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
  name.value=''
  applySelection()
}
function applySelection(){
  if(!source.value.length){entries.value=[];return}
  try{
    const batch=directoryEntries(source.value,includeUnknown.value)
    unknown.value=batch.unknown
    entries.value=batch.entries
    if(!name.value)name.value=Array.from(batch.folder.trim()||'Фотоотчёт').slice(0,120).join('')
    error.value=''
  }catch(err){entries.value=[];error.value=errorText(err)}
}
watch(includeUnknown,applySelection)
function submit(){
  if(!entries.value.length||(!props.target&&!validName.value))return
  upload.enqueue({kind:'fo',name:props.target?.name||name.value.trim(),entries:[...entries.value],
    autoProcess:autoProcess.value,threshold:autoThreshold.value,resumeBatchId:props.target?.id})
}
</script>
<template>
<form class="panel stack" aria-label="Загрузка фотографий" @submit.prevent="submit">
  <p v-if="target" class="meta">Выберите исходную папку для ФО «{{target.name}}». Уже сохранённые файлы не будут отправлены повторно.</p>
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
  <label v-if="entries.length&&!target" class="field">
    Название фотоотчёта
    <input v-model="name" maxlength="120" required aria-describedby="fo-upload-name-hint"/>
  </label>
  <p v-if="entries.length&&!target" id="fo-upload-name-hint" class="meta">Если такое название уже есть, добавим номер. Файлы будут загружены в отдельный фотоотчёт.</p>
  <div v-if="entries.length" class="row wrap between">
    <span class="meta">{{entries.length.toLocaleString('ru-RU')}} файлов · {{bytes(total)}}</span>
    <UiButton kind="primary" type="submit" :disabled="!target&&!validName">{{target?'Продолжить':'Загрузить'}}</UiButton>
  </div>
  <label v-if="entries.length&&!target" class="row wrap" style="gap:10px;align-items:center">
    <input v-model="autoProcess" type="checkbox" @change="chosenAuto=true"
      aria-label="Обработать после загрузки"/>
    <span>Обработать поддерживаемые фото после загрузки</span>
  </label>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
</form>
</template>
