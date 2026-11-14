<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {ALLOWED,MAX_IMAGE_UPLOAD_BYTES} from '../../utils/upload'
import type {UploadEntry} from '../../utils/upload'
import {useReferenceTransfer} from '../../composables/useReferenceTransfer'
import {useUploadSettingsStore} from '../../stores/uploadSettings'
import {bytes} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import ReferenceImportReview from './ReferenceImportReview.vue'
import ReferenceTransferProgress from './ReferenceTransferProgress.vue'

const props=defineProps<{selectedSam:string;label:string}>()
const emit=defineEmits<{(e:'finished',message:string,queued:boolean):void;(e:'state',busy:boolean,percent:number,phase:string):void}>()
const uploadSettings=useUploadSettingsStore(),transfer=useReferenceTransfer()
const files=ref<UploadEntry[]>([]),issues=ref<string[]>([]),target=ref('')
const total=computed(()=>files.value.reduce((sum,item)=>sum+item.file.size,0))
watch([transfer.busy,transfer.percent,transfer.phase],()=>emit('state',transfer.busy.value,transfer.percent.value,transfer.phase.value),{immediate:true})
const ready=computed(()=>!!files.value.length&&!issues.value.length&&
  !!props.selectedSam&&target.value===props.selectedSam&&!transfer.busy.value)

function choose(event:Event){
  const input=event.target as HTMLInputElement
  const picked=Array.from(input.files||[])
  input.value=''
  transfer.reset()
  files.value=[];issues.value=[];target.value=props.selectedSam
  for(const file of picked){
    if(!ALLOWED.test(file.name)){issues.value.push(file.name+': неподдерживаемый формат');continue}
    if(!file.size){issues.value.push(file.name+': пустой файл');continue}
    if(file.size>MAX_IMAGE_UPLOAD_BYTES){issues.value.push(file.name+': файл больше 60 МБ');continue}
    files.value.push({file,relative:file.name})
  }
}

async function upload(){
  if(!ready.value)return
  if(transfer.approved.value){await accept();return}
  const current=files.value.map(entry=>({sam:target.value,entry}))
  await transfer.inspect(current)
}

async function accept(){
  if(transfer.review.value&&!transfer.review.value.newFiles.length){
    emit('finished','Все выбранные фото уже есть в библиотеке. В очередь ничего не добавлено.',false)
    return
  }
  const result=await transfer.start(uploadSettings.parallelUploads)
  if(result){
    files.value=[];issues.value=[]
    const queued=result.state==='queued'
    emit('finished',queued?'Файлы приняты. Подготовка образцов поставлена в очередь.':
      'Все выбранные фото уже есть в библиотеке. В очередь ничего не добавлено.',queued)
  }
}
</script>

<template>
<ReferenceImportReview v-if="transfer.review.value" :review="transfer.review.value"
  @confirm="accept" @cancel="transfer.reset()"/>
<div v-else class="stack">
  <p class="meta">Добавление фотографий в уже выбранную конструкцию. Названия самих файлов свободные.
    Существующие образцы сохраняются, одинаковые по содержимому фото не дублируются.</p>
  <div v-if="!selectedSam" class="alert">Сначала выберите конструкцию в списке.</div>
  <template v-else>
    <strong>{{label}}</strong>
    <label class="upload-drop" :style="{opacity:transfer.busy.value?'.5':'1'}">
      <input type="file" multiple accept=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff"
        :disabled="transfer.busy.value" @change="choose"/>
      <strong>Выбрать фотографии</strong>
      <div class="meta">Без папок и специальных названий</div>
    </label>
    <div v-if="files.length||issues.length" class="stack-sm">
      <div class="row between wrap">
        <span class="meta">{{files.length}} фото · {{bytes(total)}}</span>
        <div class="row">
          <UiButton v-if="transfer.busy.value" kind="danger" @click="transfer.pause()">Пауза</UiButton>
          <UiButton v-else kind="primary" :disabled="!ready" @click="upload">
            {{transfer.approved.value?'Продолжить загрузку':'Добавить фото'}}
          </UiButton>
        </div>
      </div>
      <div v-if="issues.length" class="alert error" role="alert">
        <strong>Исправьте {{issues.length}} неподходящих файлов перед загрузкой:</strong>
        <div v-for="(issue,index) in issues" :key="index" style="overflow-wrap:anywhere">{{issue}}</div>
      </div>
    </div>
    <ReferenceTransferProgress v-if="transfer.approved.value" :completed="transfer.completed.value"
      :total-files="transfer.totalFiles.value" :duplicates="transfer.duplicates.value" :sent-bytes="transfer.sentBytes.value"
      :total-bytes="transfer.totalBytes.value" :percent="transfer.percent.value"/>
    <div v-if="transfer.phase.value" class="meta" role="status">{{transfer.phase.value}}</div>
    <div v-if="transfer.error.value" class="alert error" role="alert">{{transfer.error.value}}</div>
  </template>
</div>
</template>
