<script setup lang="ts">
import {useSessionStore} from '../../../stores/session'
const session=useSessionStore()
import {onMounted,ref} from 'vue'
import {systemApi} from '../../../api/system'
import {bytes,date,errorText} from '../../../utils/format'
import {usePolling} from '../../../composables/usePolling'
import type {StorageUsage} from '../../../types/api'
import UiButton from '../../../components/ui/UiButton.vue'
import LoadingSkeleton from '../../../components/ui/LoadingSkeleton.vue'
import StorageOverview from './StorageOverview.vue'
import StorageTechnical from './StorageTechnical.vue'
import StorageControl from './StorageControl.vue'
import StorageTemporary from './StorageTemporary.vue'
import StorageDiagnostics from './StorageDiagnostics.vue'
import StorageMaintenance from './StorageMaintenance.vue'
import StorageLimits from './StorageLimits.vue'
defineProps<{mode:'storage'|'limits'}>()
const diagnostics=ref(false)
const usage=ref<StorageUsage|null>(null),loading=ref(false),error=ref('')
async function refresh(){
  if(!session.can('storage.view'))return
  if(loading.value)return
  loading.value=true
  try{usage.value=await systemApi.usage();error.value=''}
  catch(e){error.value=errorText(e)}finally{loading.value=false}
}
onMounted(()=>void refresh())
usePolling(refresh,15000)
</script>
<template>
  <div class="stack storage-center">
    <template v-if="mode==='storage'">
      <section class="panel stack">
        <div class="row between wrap">
          <h2>Хранилище</h2><UiButton :loading="loading" @click="refresh">Обновить показатели</UiButton>
        </div>
        <p v-if="error" role="alert" class="alert error">{{error}}<template v-if="usage"> · Показаны последние полученные данные.</template></p>
        <StorageOverview v-if="usage" :usage="usage" :failed="!!error"/>
        <LoadingSkeleton v-else-if="loading" variant="lines" label="Загружаем показатели хранилища"/>
        <p v-else class="meta">Показатели пока недоступны.</p>
      </section>
      <section class="panel stack">
        <button v-if="session.can('storage.diagnostics')" class="btn secondary diagnostics-toggle" :aria-expanded="diagnostics" @click="diagnostics=!diagnostics">Диагностика хранилища <span aria-hidden="true">{{diagnostics?'−':'+'}}</span></button>
        <template v-if="diagnostics&&session.can('storage.diagnostics')">
          <div class="row wrap meta"><span>Измерение: {{date(usage?.registry?.sampled_at)}}</span></div>
          <StorageControl :usage="usage" :failed="!!error" @refresh="refresh"/>
          <StorageTechnical v-if="usage" :usage="usage"/>
          <StorageDiagnostics :usage="usage" @refresh="refresh"/>
        </template>
      </section>
    </template>
    <template v-else>
      <StorageLimits v-if="session.can('storage.limits')" @refresh="refresh"/>
      <section v-if="session.can('logs.usage')&&session.can('storage.view')" class="panel stack">
        <h2>Лимиты журналов MAP</h2>
        <div v-for="(row,name) in usage?.journals?.services||{}" :key="name" class="row between wrap"><span>{{name}}</span><strong>{{bytes(row.bytes)}} / {{bytes(row.budget_bytes)}}{{row.partial?' (частично)':''}}</strong></div>
        <p v-if="!usage?.journals" class="meta">Сведения пока недоступны.</p>
      </section>
      <StorageTemporary v-if="session.can('storage.diagnostics')" :registry="usage?.registry"/>
      <StorageMaintenance v-if="session.can('storage.maintenance')||session.can('system.retention_view')" @refresh="refresh"/>
    </template>
  </div>
</template>
<style scoped>.storage-center{min-width:0}.diagnostics-toggle{width:100%;display:flex;justify-content:space-between;white-space:normal;text-align:left}</style>
