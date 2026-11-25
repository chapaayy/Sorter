<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {systemApi} from '../../../api/system'
import {date,errorText} from '../../../utils/format'
import {usePolling} from '../../../composables/usePolling'
import type {StorageUsage} from '../../../types/api'
import UiButton from '../../../components/ui/UiButton.vue'
import LoadingSkeleton from '../../../components/ui/LoadingSkeleton.vue'
import StorageOverview from './StorageOverview.vue'
import StorageControl from './StorageControl.vue'
import StorageAccounts from './StorageAccounts.vue'
import StorageTemporary from './StorageTemporary.vue'
import StorageDiagnostics from './StorageDiagnostics.vue'
import StorageMaintenance from './StorageMaintenance.vue'
import StorageLimits from './StorageLimits.vue'
const tabs=[['overview','Обзор'],['control','Контроль'],['accounts','По аккаунтам'],['temporary','Временные данные'],['limits','Лимиты'],['diagnostics','Диагностика'],['maintenance','Обслуживание']] as const
const active=ref<(typeof tabs)[number][0]>('overview')
const usage=ref<StorageUsage|null>(null),loading=ref(false),error=ref('')
async function refresh(){
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
    <section class="panel stack">
      <div class="row between wrap">
        <div><h2>Хранилище</h2><p class="meta">Единый учёт файлов MAP и инфраструктуры.</p></div>
        <UiButton :loading="loading" @click="refresh">Обновить показатели</UiButton>
      </div>
      <p v-if="error" role="alert" class="alert error">{{error}}<template v-if="usage"> · Показаны последние полученные данные.</template></p>
      <div class="row wrap meta" aria-live="polite">
        <span>Измерение: {{date(usage?.registry?.sampled_at)}}</span>
        <span v-if="usage?.registry" class="status" :class="usage.registry.partial?'':'ok'">
          {{usage.registry.reconciliation_requested?'Сверка запрошена':usage.registry.stale?'Данные устарели':usage.registry.reconciling?'Идёт сверка':usage.registry.partial?'Неполный снимок':'Актуальный снимок'}}
        </span>
      </div>
      <nav aria-label="Разделы хранилища" class="storage-nav">
        <button v-for="[key,label] in tabs" :key="key" class="btn small" :class="active===key?'primary':'secondary'" :aria-pressed="active===key" @click="active=key">{{label}}</button>
      </nav>
    </section>
    <template v-if="active==='overview'">
      <StorageOverview v-if="usage" :usage="usage"/>
      <LoadingSkeleton v-else-if="loading" variant="lines" label="Загружаем показатели хранилища"/>
      <p v-else class="meta">Показатели пока недоступны.</p>
    </template>
    <StorageControl v-else-if="active==='control'" :usage="usage"/>
    <StorageAccounts v-else-if="active==='accounts'"/>
    <StorageTemporary v-else-if="active==='temporary'" :registry="usage?.registry"/>
    <StorageLimits v-else-if="active==='limits'" @refresh="refresh"/>
    <StorageDiagnostics v-else-if="active==='diagnostics'" :usage="usage" @refresh="refresh"/>
    <StorageMaintenance v-else-if="active==='maintenance'" @refresh="refresh"/>
  </div>
</template>
<style scoped>.storage-center{min-width:0}.storage-nav{display:flex;flex-wrap:wrap;gap:6px}.storage-nav .btn{white-space:normal}.storage-nav .btn[aria-pressed=true]{font-weight:650}</style>
