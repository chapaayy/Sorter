<script setup lang="ts">
import {computed,ref} from 'vue'
import {referenceApi} from '../../api/references'
import type {ImportPlan,ImportPlanEntry} from '../../api/references'
import {inspectReferenceDirectory} from '../../utils/referenceSelection'
import type {ReferenceSelection} from '../../utils/referenceSelection'
import {useReferenceTransfer} from '../../composables/useReferenceTransfer'
import {useUploadSettingsStore} from '../../stores/uploadSettings'
import {useNoticeStore} from '../../stores/notice'
import {bytes,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'

const props=defineProps<{disabled:boolean;staged?:boolean}>()
const emit=defineEmits<{(e:'finished'):void}>()
const uploadSettings=useUploadSettingsStore(),notice=useNoticeStore()
const transfer=useReferenceTransfer(!!props.staged)
const selection=ref<ReferenceSelection|null>(null),plan=ref<ImportPlan|null>(null)
const checking=ref(false),error=ref('')
let revision=0
const errors=computed(()=>[
  ...(selection.value?.errors||[]),
  ...(plan.value?.errors||[]).map(issue=>({path:issue.folder,reason:issue.reason}))
])
const planById=computed<Record<string,ImportPlanEntry>>(()=>
  Object.fromEntries((plan.value?.entries||[]).map(entry=>[entry.sam,entry])))
const existingCount=computed(()=>plan.value?.entries.filter(entry=>entry.existing).length||0)
const ready=computed(()=>!props.disabled&&!checking.value&&!transfer.busy.value&&
  !!selection.value?.tasks.length&&!!plan.value&&!errors.value.length)

async function choose(event:Event){
  const input=event.target as HTMLInputElement
  const files=Array.from(input.files||[])
  input.value=''
  const current=++revision
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

async function upload(){
  if(!ready.value||!selection.value)return
  error.value=''
  // Server verification is repeated immediately before beginning the batch.
  checking.value=true
  try{
    const checked=await referenceApi.importPreview(selection.value.folders.map(folder=>folder.folder))
    plan.value=checked
    if(checked.errors.length)return
  }catch(err){error.value='Повторная проверка не удалась: '+errorText(err);return}
  finally{checking.value=false}
  if(props.disabled)return
  const items=selection.value.tasks
  const success=await transfer.start(items,uploadSettings.parallelUploads)
  if(success){
    notice.add(props.staged
      ?'Файлы сохранены. Подготовка образцов поставлена в общую очередь.'
      :'Библиотека обновлена: обработано '+items.length+
        ' фото, совпадений '+transfer.duplicates.value+'. Ничего не удалено.','ok')
    selection.value=null;plan.value=null
    emit('finished')
  }
}
</script>

<template>
<div class="stack">
  <p class="meta">Выберите общую папку. Внутри — папки конструкций строго вида
    <strong>SAM 0004 — Гагарина 64</strong> или <strong>TLT 3245 — Южное шоссе 10</strong>.
    Существующие конструкции дополняются, новые создаются. Фото не заменяются и не удаляются.</p>
  <label class="upload-drop" :style="{opacity:disabled||transfer.busy.value?'.5':'1'}">
    <input type="file" webkitdirectory directory multiple
      :disabled="disabled||transfer.busy.value||checking" @change="choose"/>
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
      <div class="row wrap meta">
        <span>{{existingCount}} существующих конструкций — дополним</span>
        <span>{{plan.entries.length-existingCount}} новых — создадим</span>
        <span>Объём: {{bytes(selection.totalBytes)}}</span>
      </div>
      <div class="stack-sm" style="max-height:270px;overflow-y:auto">
        <div v-for="folder in selection.folders" :key="folder.sam" class="row between wrap"
          style="padding:9px 0;border-bottom:1px solid var(--border-subtle)">
          <div>
            <strong>{{folder.folder}}</strong>
            <div class="meta">{{planById[folder.sam]?.existing?'Дополнение существующей':'Новая конструкция'}}</div>
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
        <UiButton v-if="transfer.busy.value" kind="danger" @click="transfer.pause()">Пауза</UiButton>
        <UiButton v-else kind="primary" :disabled="!ready" @click="upload">
          {{staged?'Загрузить и подготовить':'Создать и дополнить'}}
        </UiButton>
      </div>
    </div>
    <div v-if="transfer.busy.value||transfer.completed.value" class="stack-sm">
      <div class="row between meta">
        <span>Готово {{transfer.completed.value}} из {{selection.tasks.length}} · совпадений {{transfer.duplicates.value}}</span>
        <span>{{bytes(transfer.sentBytes.value)}} / {{bytes(selection.totalBytes)}}</span>
      </div>
      <div class="progress-track"><span class="progress-fill"
        :style="{width:selection.totalBytes?100*transfer.sentBytes.value/selection.totalBytes+'%':'0%'}"/></div>
    </div>
    <div v-if="transfer.phase.value" class="meta" role="status">{{transfer.phase.value}}</div>
    <div v-if="transfer.error.value" class="alert error" role="alert">{{transfer.error.value}}</div>
  </div>
</div>
</template>
