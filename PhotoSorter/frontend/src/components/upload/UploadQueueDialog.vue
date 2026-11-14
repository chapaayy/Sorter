<script setup lang="ts">
import {ref} from 'vue'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {bytes} from '../../utils/format'
import {uploadPercent,uploadStatusLabel,uploadKindLabel} from '../../utils/transferPresentation'
import UiButton from '../ui/UiButton.vue'
import UploadDialog from './UploadDialog.vue'

const upload=useUploadCenterStore()
const confirmCancel=ref<number|null>(null)
function confirm(id:number){
  upload.cancel(id)
  confirmCancel.value=null
}
</script>

<template>
  <UploadDialog title="Очередь загрузок" heading-id="upload-queue-heading" @close="upload.closeQueue()">
    <p class="meta upload-queue-intro">Передача файлов на сайт. Обработка MegaLoc идёт в отдельной очереди.</p>
    <p v-if="!upload.rows.length" role="status">Нет активных и ожидающих загрузок.</p>
    <ol v-else class="upload-queue-list stack-sm" aria-label="Загрузки на сайт">
      <li v-for="row in upload.rows" :key="row.id" class="upload-queue-row stack-sm"
        :class="{'upload-queue-row-current':row.id===upload.current?.id}">
        <div class="row between wrap">
          <div class="upload-queue-name">
            <span class="meta">{{uploadKindLabel(row.kind)}}</span>
            <strong>{{row.name}}</strong>
          </div>
          <span class="status">{{uploadStatusLabel(row.status)}}</span>
        </div>
        <div v-if="row.status==='waiting'" class="meta">{{row.totalFiles}} файлов · {{bytes(row.totalBytes)}}</div>
        <template v-else>
          <div class="row between wrap meta">
            <span>{{row.completed}} из {{row.totalFiles}} файлов<template v-if="row.duplicates"> · дублей пропущено: {{row.duplicates}}</template></span>
            <strong>{{uploadPercent(row)}}%</strong>
          </div>
          <div class="progress-track" role="progressbar" :aria-label="'Загрузка '+row.name"
            :aria-valuenow="uploadPercent(row)" aria-valuemin="0" aria-valuemax="100">
            <span class="progress-fill" :style="{width:uploadPercent(row)+'%'}"/>
          </div>
          <div class="meta">{{bytes(row.sentBytes)}} / {{bytes(row.totalBytes)}}<template v-if="row.status==='running'&&row.phase"> · {{row.phase}}</template></div>
          <div v-if="row.error" class="alert error" role="alert">{{row.error}}</div>
        </template>
        <div v-if="confirmCancel===row.id" class="stack-sm">
          <p class="meta">Передача остановится. Уже переданные файлы не удалятся, их можно будет докачать позже.</p>
          <div class="row wrap">
            <UiButton small kind="danger" @click="confirm(row.id)">Да, отменить</UiButton>
            <UiButton small @click="confirmCancel=null">Оставить</UiButton>
          </div>
        </div>
        <div v-else class="row wrap">
          <UiButton v-if="row.status==='running'" small @click="upload.pause(row.id)">Приостановить</UiButton>
          <UiButton v-if="row.status==='paused'||row.status==='failed'" small kind="primary" @click="upload.continueUpload(row.id)">
            {{row.status==='failed'?'Повторить':'Продолжить'}}
          </UiButton>
          <UiButton v-if="row.status==='waiting'" small @click="upload.cancel(row.id)">Убрать из очереди</UiButton>
          <UiButton v-else-if="row.status!=='cancelling'" small @click="confirmCancel=row.id">Отменить загрузку</UiButton>
        </div>
      </li>
    </ol>
  </UploadDialog>
</template>
