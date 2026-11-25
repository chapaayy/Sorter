<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue'
import {referenceApi} from '../../api/references'
import {regionApi} from '../../api/regions'
import type {ImportPlan,ImportPlanEntry} from '../../api/references'
import {inspectReferenceDirectory} from '../../utils/referenceSelection'
import type {ReferenceSelection} from '../../utils/referenceSelection'
import {useReferencePreflight} from '../../composables/useReferencePreflight'
import {useUploadCenterStore} from '../../stores/uploadCenter'
import {ALL_DUPLICATES} from '../../utils/referenceTransfer'
import {bytes,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import ReferenceImportReview from './ReferenceImportReview.vue'


const emit=defineEmits<{(e:'noChanges',message:string):void;(e:'checking',busy:boolean):void}>()
const uploadCenter=useUploadCenterStore(),transfer=useReferencePreflight()
const selection=ref<ReferenceSelection|null>(null),plan=ref<ImportPlan|null>(null)
const checking=ref(false),starting=ref(false),registeringRegions=ref(false),error=ref('')
let revision=0
onUnmounted(()=>{revision++})
const errors=computed(()=>[
  ...(selection.value?.errors||[]),
  ...(plan.value?.errors||[]).map(issue=>({path:issue.folder,reason:issue.reason}))
])
const planById=computed<Record<string,ImportPlanEntry>>(()=>
  Object.fromEntries((plan.value?.entries||[]).map(entry=>[entry.sam,entry])))
const existingCount=computed(()=>plan.value?.entries.filter(entry=>entry.existing).length||0)
watch([starting,transfer.busy],()=>emit('checking',starting.value||transfer.busy.value),{immediate:true})
const ready=computed(()=>!checking.value&&!transfer.busy.value&&
  !!selection.value?.tasks.length&&!!plan.value&&!errors.value.length&&
  !plan.value.new_regions.length&&!registeringRegions.value)

async function choose(event:Event){
  const input=event.target as HTMLInputElement
  const files=Array.from(input.files||[])
  input.value=''
  const current=++revision
  transfer.reset()
  selection.value=files.length?inspectReferenceDirectory(files):null
  plan.value=null;error.value=''
  if(!selection.value)return
  if(!selection.value.folders.length){
    error.value='Нет ни одной папки с корректным названием. Проверьте ошибки ниже.'
    return
  }
  checking.value=true
  try{
    const checked=await referenceApi.importPreview(selection.value.folders.map(folder=>folder.folder))
    if(revision===current)plan.value=checked
  }catch(err){if(revision===current)error.value='Не удалось проверить библиотеку на сервере: '+errorText(err)}
  finally{if(revision===current)checking.value=false}
}

async function createUnknownRegions(){
  const missing=plan.value?.new_regions||[]
  if(!missing.length||registeringRegions.value||!selection.value)return
  registeringRegions.value=true;error.value=''
  try{
    for(const code of missing)await regionApi.create(code)
    plan.value=await referenceApi.importPreview(selection.value.folders.map(f=>f.folder))
  }catch(e){error.value='Не удалось создать регионы: '+errorText(e)}
  finally{registeringRegions.value=false}
}
async function upload(){
  if(!ready.value||!selection.value)return
  error.value=''
  // Server verification is repeated immediately before beginning the batch.
  starting.value=true
  checking.value=true
  const current=revision
  const {folders,tasks}=selection.value
  try{
    const checked=await referenceApi.importPreview(folders.map(folder=>folder.folder))
    if(current!==revision)return
    plan.value=checked
    if(checked.errors.length)return
  }catch(err){error.value='Повторная проверка не удалась: '+errorText(err);return}
  finally{checking.value=false;starting.value=false}
  await transfer.inspect(tasks)
}

function accept(){
  const review=transfer.review.value
  if(!review)return
  if(!review.newFiles.length){emit('noChanges',ALL_DUPLICATES);return}
  const name=review.newFiles[0]!.entry.relative.split('/')[0]||'Библиотека'
  uploadCenter.enqueue({kind:'references',name,review,success:'Образцы загружены. Подготовка поставлена в общую очередь.'})
}
</script>

<template>
<ReferenceImportReview v-if="transfer.review.value" :review="transfer.review.value"
  @confirm="accept" @cancel="transfer.reset()"/>
<div v-else class="stack">
  <p class="meta">Выберите общую папку. Внутри — папки конструкций строго вида
    <strong>SAM 0004 — Гагарина 64</strong> или <strong>TLT 3245 — Южное шоссе 10</strong>.
    Внутри конструкции можно разместить папки A, A1–A3, B, B1–B3 и Неназначенные.
    Фото без папки стороны остаются неназначенными. Существующие фото не заменяются и не удаляются.</p>
  <label class="upload-drop" :style="{opacity:transfer.busy.value?'.5':'1'}">
    <input type="file" webkitdirectory directory multiple
      :disabled="transfer.busy.value||checking" @change="choose"/>
    <strong>Выбрать папку библиотеки</strong>
    <div class="meta">Сначала проверим все выбранные файлы и названия папок</div>
  </label>
  <div v-if="selection" class="stack">
    <div class="grid3">
      <div><strong>{{selection.scanned}}</strong><div class="meta">Всего файлов выбрано</div></div>
      <div><strong>{{selection.tasks.length}}</strong><div class="meta">Подходящих изображений</div></div>
      <div><strong>{{selection.folders.length}}</strong><div class="meta">Конструкций</div></div>
    </div>
    <div v-if="selection.skipped.length" class="alert" role="status">
      <strong>Пропущено служебных файлов: {{selection.skipped.length}}</strong>
      <p class="meta" style="margin:6px 0">Эти файлы Windows/macOS не являются фотографиями и не будут загружены.</p>
      <div class="stack-sm" style="max-height:140px;overflow:auto">
        <div v-for="item in selection.skipped" :key="item.path" style="overflow-wrap:anywhere">
          {{item.path}}
        </div>
      </div>
    </div>
    <div v-if="checking" class="meta">Проверяем названия и существующую библиотеку на сервере…</div>
    <template v-else-if="plan">
      <div v-if="plan.new_regions.length" class="alert warning" role="status">
        <strong>Новые коды регионов: {{plan.new_regions.join(', ')}}</strong>
        <p class="meta">Проверьте коды в названиях папок — опечатка создаст отдельный регион.</p>
        <UiButton small kind="primary" :loading="registeringRegions"
          @click="createUnknownRegions">Подтвердить и добавить регионы</UiButton>
      </div>
      <div class="row wrap meta">
        <span>В библиотеке: {{existingCount}}</span>
        <span>Новых конструкций: {{plan.entries.length-existingCount}}</span>
        <span>Выбрано: {{bytes(selection.totalBytes)}}</span>
      </div>
      <div class="stack-sm" style="max-height:270px;overflow-y:auto">
        <div v-for="folder in selection.folders" :key="folder.sam" class="row between wrap"
          style="padding:9px 0;border-bottom:1px solid var(--border-subtle)">
          <div>
            <strong>{{folder.folder}}</strong>
            <div class="meta">{{planById[folder.sam]?.existing?'Уже в библиотеке':'Новая конструкция'}}</div>
            <div class="meta">Со стороной: {{selection.tasks.filter(t=>t.sam===folder.sam&&t.side).length}}</div>
          </div>
          <span class="meta">{{folder.count}} фото</span>
        </div>
      </div>
    </template>
    <div v-if="errors.length" class="alert error" role="alert">
      <strong>Найдено {{errors.length}} ошибок. Загрузка заблокирована.</strong>
      <p style="margin:8px 0">Исправьте названия папок или неподходящие файлы, затем выберите папку снова.</p>
      <div class="stack-sm" style="max-height:260px;overflow:auto">
        <div v-for="(issue,index) in errors" :key="index" style="overflow-wrap:anywhere">
          {{issue.path}} — {{issue.reason}}
        </div>
      </div>
    </div>
    <div v-if="error" class="alert error" role="alert">{{error}}</div>
    <div class="row between wrap">
      <span class="meta">Учтено {{selection.scanned}}: {{selection.tasks.length}} фото · {{selection.skipped.length}} служебных пропущено · {{selection.errors.length}} ошибок</span>
      <div class="row">
        <UiButton v-if="transfer.busy.value" kind="danger" @click="transfer.pause()">Остановить проверку</UiButton>
        <UiButton v-else kind="primary" :disabled="!ready" @click="upload">
          Загрузить и подготовить
        </UiButton>
      </div>
    </div>
    <div v-if="transfer.phase.value" class="meta" role="status">{{transfer.phase.value}}</div>
    <div v-if="transfer.error.value" class="alert error" role="alert">{{transfer.error.value}}</div>
  </div>
</div>
</template>
