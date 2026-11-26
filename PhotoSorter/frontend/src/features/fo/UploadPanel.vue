<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {useSessionStore} from '../../stores/session'
const session=useSessionStore()
const canAuto=computed(()=>session.can('photos.auto')&&session.can('photos.process')&&session.can('photos.view'))
import type {MediaProfile} from '../../types/api'
import {runApi} from '../../api/runs'
import {regionApi,type Region} from '../../api/regions'
import RegionChips from '../../components/regions/RegionChips.vue'
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
const regionRows=ref<Region[]>([]),selectedRegions=ref<string[]>([]),regionsLoading=ref(true)
const reportDate=ref(''),useProcessingDate=ref(false)
const validReportDate=computed(()=>useProcessingDate.value||/^\d{4}-\d{2}-\d{2}$/.test(reportDate.value))
const chosenAuto=ref(false)
const imageFormat=ref<MediaProfile['image_format']>('jpg'),videoFormat=ref<MediaProfile['video_format']>('mp4')
const total=computed(()=>entries.value.reduce((sum,e)=>sum+e.file.size,0))
const validName=computed(()=>!!name.value.trim()&&Array.from(name.value.trim()).length<=120)
onMounted(async()=>{
  if(props.target)return
  if(!canAuto.value){regionsLoading.value=false;return}
  try{regionRows.value=(await regionApi.list()).regions}
  catch(e){error.value='Не удалось загрузить регионы: '+errorText(e)}
  finally{regionsLoading.value=false}
  try{
    const defaults=await runApi.autoSettings()
    if(!chosenAuto.value)autoProcess.value=canAuto.value&&defaults.auto_process_new_batches
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
  if(!canAuto.value)autoProcess.value=false
  if(!entries.value.length||(!props.target&&(!validName.value||!validReportDate.value))
     ||(!props.target&&autoProcess.value&&!selectedRegions.value.length))return
  upload.enqueue({kind:'fo',name:props.target?.name||name.value.trim(),entries:[...entries.value],
    autoProcess:autoProcess.value,threshold:autoThreshold.value,
    regions:autoProcess.value?[...selectedRegions.value]:[],resumeBatchId:props.target?.id,
    profile:{image_format:imageFormat.value,video_format:videoFormat.value},
    reportDateMode:useProcessingDate.value?'processing':'manual',
    reportDate:useProcessingDate.value?null:reportDate.value})
}
</script>
<template>
<form class="panel stack" aria-label="Загрузка фотографий" @submit.prevent="submit">
  <p v-if="target" class="meta">Выберите исходную папку для ФО «{{target.name}}». Уже сохранённые файлы не будут отправлены повторно.</p>
  <label class="upload-drop">
    <input type="file" multiple webkitdirectory directory @change="choose"/>
    <span style="font-size:27px;color:var(--muted)">▤</span><br/>
    <strong>Выбрать папку с фото и видео</strong>
    <p class="meta" style="margin:6px 0 0">Фото и видео в одной папке · до 2 ГиБ на файл</p>
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
  <label v-if="entries.length&&!target" class="field">Дата фотоотчёта
    <input v-model="reportDate" type="date" :disabled="useProcessingDate" :required="!useProcessingDate" aria-label="Дата фотоотчёта"/>
  </label>
  <label v-if="entries.length&&!target" class="row wrap">
    <input v-model="useProcessingDate" type="checkbox"/>
    <span>Использовать дату обработки</span>
  </label>
  <div v-if="entries.length&&!target" class="row wrap" aria-label="Форматы готовых файлов">
    <label class="field">Фото на выходе<select v-model="imageFormat"><option value="jpg">JPG</option><option value="png">PNG</option></select></label>
    <label class="field">Видео на выходе<select v-model="videoFormat"><option value="mp4">MP4</option><option value="webm">WebM</option></select></label>
  </div>
  <p v-if="entries.length&&!target" class="meta">Перекодируются только несовместимые файлы. Оригиналы останутся на сервере.</p>
  <div v-if="entries.length" class="row wrap between">
    <span class="meta">{{entries.length.toLocaleString('ru-RU')}} файлов · {{bytes(total)}}</span>
    <UiButton kind="primary" type="submit"
      :disabled="!target&&(!validName||!validReportDate||(autoProcess&&!selectedRegions.length)||regionsLoading&&autoProcess)">
      {{target?'Продолжить':'Загрузить'}}</UiButton>
  </div>
  <label v-if="entries.length&&!target&&canAuto" class="row wrap" style="gap:10px;align-items:center">
    <input v-model="autoProcess" type="checkbox" @change="chosenAuto=true"
      aria-label="Обработать после загрузки"/>
    <span>Отсортировать фото и видео после загрузки</span>
  </label>
  <div v-if="entries.length&&!target&&canAuto&&autoProcess" class="panel stack-sm">
    <RegionChips v-model="selectedRegions" :regions="regionRows" :disabled="regionsLoading"/>
    <p class="meta">Выбор сохранится в партии. После загрузки отдельное окно не потребуется.</p>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
</form>
</template>
