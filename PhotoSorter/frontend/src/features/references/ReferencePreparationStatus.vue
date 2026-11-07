<script setup lang="ts">
import {onMounted,ref} from 'vue'
import type {LibraryStatus} from '../../api/libraryNotices'
import {referenceImportsApi} from '../../api/referenceImports'
import type {ImportSessionSummary} from '../../api/referenceImports'
import {usePolling} from '../../composables/usePolling'
import {date,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'

const props=defineProps<{library:LibraryStatus|null}>()
const sessions=ref<ImportSessionSummary[]>([]),error=ref(''),loading=ref(false)
async function refresh(){
  if(!props.library?.staged_imports_enabled)return
  loading.value=true
  try{
    const response=await referenceImportsApi.list(15)
    sessions.value=response.sessions
    error.value=''
  }catch(e){error.value=errorText(e)}
  finally{loading.value=false}
}
onMounted(()=>void refresh())
usePolling(refresh,6000)
const title=(session:ImportSessionSummary)=>{
  if(session.state==='uploading')return 'Загрузка образцов'
  if(session.preparation_state==='pending')return 'Ожидает подготовки'
  if(session.preparation_state==='queued')return 'Подготовка в очереди'
  if(session.preparation_state==='running')return 'Подготовка образцов'
  if(session.preparation_state==='completed')return 'Образцы опубликованы'
  if(session.preparation_state==='stopped')return 'Обновление пропущено'
  return 'Требуется исправить подготовку'
}
</script>
<template>
<section class="panel stack" aria-label="Публикация и подготовка образцов">
  <div class="row between wrap">
    <h2 style="margin:0">Загрузка и подготовка</h2>
    <RouterLink to="/queue" class="btn small">Открыть очередь</RouterLink>
  </div>
  <div class="row wrap between">
    <div>
      <span class="label">Опубликованная библиотека</span>
      <strong>{{library?.current_version?'Версия '+library.current_version:'Версия пока не создана'}}</strong>
      <div class="meta">{{library?.published_references??0}} образцов
        <template v-if="library?.published_at"> · обновлено {{date(library.published_at)}}</template>
      </div>
    </div>
    <span class="status" :class="library?.baseline_state==='ready'?'ok':'danger'">
      {{library?.baseline_state==='ready'?'Библиотека готова':'Требует проверки'}}
    </span>
  </div>
  <div v-if="library?.baseline_error" class="alert error" role="alert">{{library.baseline_error}}</div>
  <div v-if="!library?.staged_imports_enabled" class="meta">
    Поэтапная загрузка образцов пока не включена на сервере.
  </div>
  <template v-else>
    <div class="row between wrap"><strong>Последние импорты</strong>
      <UiButton small :loading="loading" @click="refresh">Обновить</UiButton></div>
    <div v-if="error" class="alert error" role="alert">{{error}}</div>
    <div v-if="!sessions.length" class="meta">Новых сессий пока нет.</div>
    <div v-for="session in sessions" :key="session.id" class="stack-sm reference-import-entry">
      <div class="row between wrap">
        <strong>{{title(session)}}</strong>
        <span class="meta">{{date(session.created_at)}}</span>
      </div>
      <div class="row wrap between">
        <span class="meta" v-if="session.state==='uploading'">
          Передано {{session.finalized+session.duplicates}}/{{session.expected_count||0}} ·
          совпадений {{session.duplicates}}
        </span>
        <span class="meta" v-else>
          Готово {{session.completed_count||0}}/{{session.total_count||session.expected_count||0}}
          · передано {{session.finalized}} · совпадений {{session.duplicates}}
        </span>
        <RouterLink v-if="session.preparation_job_id" class="meta"
          to="/queue">Задание #{{session.queue_seq}}</RouterLink>
      </div>
      <div class="progress-track" role="progressbar"
        :aria-valuenow="session.state==='uploading'?session.finalized+session.duplicates:session.completed_count||0"
        :aria-valuemax="session.state==='uploading'?session.expected_count||0:session.total_count||0"
        aria-valuemin="0">
        <span class="progress-fill" :style="{width:Math.min(100,100*
           (session.state==='uploading'?session.finalized+session.duplicates:session.completed_count||0)/
           (session.state==='uploading'?session.expected_count||1:session.total_count||1))+'%'}"/>
      </div>
      <div v-if="session.error" class="meta" role="alert">{{session.error}}</div>
    </div>
  </template>
</section>
</template>
