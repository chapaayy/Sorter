<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {ALLOWED,MAX_IMAGE_UPLOAD_BYTES} from '../../utils/upload'
import type {UploadEntry} from '../../utils/upload'
import {useReferencePreflight} from '../../composables/useReferencePreflight'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {ALL_DUPLICATES} from '../../utils/referenceTransfer'
import {bytes} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import ReferenceImportReview from './ReferenceImportReview.vue'

const props=defineProps<{selectedSam:string;label:string}>()
const emit=defineEmits<{(e:'noChanges',message:string):void;(e:'checking',busy:boolean):void}>()
const uploadCenter=useUploadCenterStore(),transfer=useReferencePreflight()
const files=ref<UploadEntry[]>([]),issues=ref<string[]>([]),target=ref('')
const total=computed(()=>files.value.reduce((sum,item)=>sum+item.file.size,0))
watch(transfer.busy,value=>emit('checking',value),{immediate:true})
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
  const current=files.value.map(entry=>({sam:target.value,entry}))
  await transfer.inspect(current)
}

function accept(updated=0){
  const review=transfer.review.value
  if(!review)return
  if(updated)uploadCenter.complete({})
  if(!review.newFiles.length){emit('noChanges',updated?'Стороны обновлены: '+updated+'. Повторной загрузки и подготовки нет.':ALL_DUPLICATES);return}
  uploadCenter.enqueue({kind:'references',name:props.label,review,success:'Файлы приняты. Подготовка образцов поставлена в очередь.'})
}
</script>

<template>
<ReferenceImportReview v-if="transfer.review.value" :review="transfer.review.value"
  @confirm="accept" @cancel="transfer.reset()" @checking="value=>emit('checking',value)"/>
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
          <UiButton v-if="transfer.busy.value" kind="danger" @click="transfer.pause()">Остановить проверку</UiButton>
          <UiButton v-else kind="primary" :disabled="!ready" @click="upload">
            Добавить фото
          </UiButton>
        </div>
      </div>
      <div v-if="issues.length" class="alert error" role="alert">
        <strong>Исправьте {{issues.length}} неподходящих файлов перед загрузкой:</strong>
        <div v-for="(issue,index) in issues" :key="index" style="overflow-wrap:anywhere">{{issue}}</div>
      </div>
    </div>
    <div v-if="transfer.phase.value" class="meta" role="status">{{transfer.phase.value}}</div>
    <div v-if="transfer.error.value" class="alert error" role="alert">{{transfer.error.value}}</div>
  </template>
</div>
</template>
