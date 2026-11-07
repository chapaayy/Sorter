<script setup lang="ts">
import {ref} from 'vue'
import {libraryNoticesApi} from '../../api/libraryNotices'
import type {LibraryEvent,LibraryStatus} from '../../api/libraryNotices'
import {date,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'

const props=defineProps<{status:LibraryStatus}>()
const emit=defineEmits<{(e:'ack',status:LibraryStatus):void}>()
const loading=ref(false),historyLoading=ref(false),error=ref(''),
  expanded=ref(false),events=ref<LibraryEvent[]>([])
async function acknowledge(){
  const id=props.status.notice_version_id
  if(!id||loading.value)return
  loading.value=true;error.value=''
  try{emit('ack',await libraryNoticesApi.acknowledge(id))}
  catch(e){error.value=errorText(e)}
  finally{loading.value=false}
}
async function showChanges(){
  if(expanded.value){expanded.value=false;return}
  historyLoading.value=true;error.value=''
  try{
    const result=await libraryNoticesApi.events(50,props.status.acknowledged_version_id)
    events.value=result.events.filter(e=>['reference_prepared','legacy_reconcile'].includes(e.event_kind))
    expanded.value=true
  }catch(e){error.value=errorText(e)}
  finally{historyLoading.value=false}
}
</script>
<template>
<section v-if="status.notice" class="panel stack" role="status"
  aria-label="Уведомление об обновлении образцов">
  <div class="row between wrap">
    <strong>Образцы обновились</strong>
    <span class="meta">{{status.pending_changes}} изменений библиотеки</span>
  </div>
  <p style="margin:0">{{status.message}}</p>
  <div class="row wrap">
    <UiButton kind="primary" small :loading="loading" @click="acknowledge">Понятно</UiButton>
    <UiButton small :loading="historyLoading" :aria-expanded="expanded"
      @click="showChanges">{{expanded?'Скрыть изменения':'Что изменилось'}}</UiButton>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <div v-if="expanded" class="stack-sm">
    <div v-for="event in events" :key="event.id" class="meta"
      style="border-top:1px solid var(--border-subtle);padding-top:9px">
      {{date(event.created_at)}} · версия {{event.version_number}} ·
      {{event.event_kind==='reference_prepared'?'Подготовлены новые образцы':'Изменён состав библиотеки'}}
      <template v-if="typeof event.details.reference_count==='number'">
        · образцов: {{event.details.reference_count}}
      </template>
    </div>
    <span v-if="!events.length" class="meta">Подробностей публикаций нет.</span>
  </div>
</section>
</template>
