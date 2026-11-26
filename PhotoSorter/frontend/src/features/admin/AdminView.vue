<script setup lang="ts">
import {ref,watch} from 'vue'
import {accountsApi} from '../../api/accounts'
import {usePolling} from '../../composables/usePolling'
import PageHeader from '../../components/ui/PageHeader.vue'
import AccessRequests from './users/AccessRequests.vue'
import StorageCenter from './storage/StorageCenter.vue'
import AccountDirectory from './users/AccountDirectory.vue'
import RolesPanel from './users/RolesPanel.vue'
import RegistrationPanel from './users/RegistrationPanel.vue'
import MapUpdater from './MapUpdater.vue'
import MegaLocSettings from '../settings/MegaLocSettings.vue'
import PerformanceSettings from '../settings/PerformanceSettings.vue'
import SystemSettings from '../settings/SystemSettings.vue'

const accountRefresh=ref(0),requestRefresh=ref(0)
const tabs=[['storage','Хранилище'],['accounts','Аккаунты'],['limits','Лимиты и хранение'],['system','Система']] as const
const active=ref<(typeof tabs)[number][0]>('storage')
const accountTab=ref<'users'|'requests'|'roles'>('users')
const pending=ref<number|null>(null)
async function count(){if(active.value!=='accounts')return;try{pending.value=(await accountsApi.registration()).pending}catch{pending.value=null}}
watch(active,()=>void count())
usePolling(count,15000)
</script>

<template>
  <PageHeader eyebrow="УПРАВЛЕНИЕ СИСТЕМОЙ" title="Администрирование"/>
  <div class="settings-layout">
    <nav aria-label="Разделы администрирования" class="admin-nav">
      <button v-for="[key,label] in tabs" :key="key" class="btn small" :class="active===key?'primary':'secondary'" :aria-pressed="active===key" @click="active=key">{{label}}</button>
    </nav>
    <section v-if="active==='storage'||active==='limits'" :aria-label="active==='storage'?'Хранилище':'Лимиты и хранение'" class="stack">
      <StorageCenter :mode="active"/>
    </section>
    <section v-else-if="active==='accounts'" aria-label="Пользователи" class="stack">
      <nav class="admin-nav" aria-label="Разделы аккаунтов">
        <button v-for="item in ([['users','Пользователи'],['requests','Заявки'],['roles','Роли']] as const)" :key="item[0]" class="btn small" :class="accountTab===item[0]?'primary':'secondary'" :aria-pressed="accountTab===item[0]" @click="accountTab=item[0]">{{item[1]}}<template v-if="item[0]==='requests'&&pending"> ({{pending}})</template></button>
      </nav>
      <template v-if="accountTab==='users'">
        <AccountDirectory :refresh-key="accountRefresh" @created="requestRefresh++"/>
      </template>
      <template v-else-if="accountTab==='requests'"><RegistrationPanel/><AccessRequests :refresh-key="requestRefresh" @approved="accountRefresh++;count()"/></template>
      <RolesPanel v-else/>
    </section>
    <div v-else class="stack">
      <section aria-label="Обновления" class="stack"><MapUpdater/></section>
      <section aria-label="MegaLoc" class="stack"><MegaLocSettings/></section>
      <section aria-label="Производительность" class="stack"><PerformanceSettings/></section>
      <section aria-label="Система" class="stack"><SystemSettings/></section>
    </div>
  </div>
</template>
<style scoped>.admin-nav{display:flex;flex-wrap:wrap;gap:8px}.admin-nav .btn{white-space:normal}.admin-nav .btn[aria-pressed=true]{font-weight:650}</style>
