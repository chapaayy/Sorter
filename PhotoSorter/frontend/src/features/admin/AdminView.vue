<script setup lang="ts">
import {computed,ref,watch} from 'vue'
import {useSessionStore} from '../../stores/session'
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

const session=useSessionStore()
const accountRefresh=ref(0),requestRefresh=ref(0)
const tabs=[['storage','Хранилище'],['accounts','Аккаунты'],['limits','Лимиты и хранение'],['system','Система']] as const
const visibleTabs=computed(()=>tabs.filter(([key])=>key==='storage'?session.can('storage.view'):key==='limits'?['storage.limits','storage.maintenance','system.retention_view','logs.usage'].some(k=>session.can(k)):key==='accounts'?['accounts.view','accounts.requests','accounts.roles'].some(k=>session.can(k)):['system.status','system.models','system.processing_view','system.performance_view','system.update_status'].some(k=>session.can(k))))
const active=ref<(typeof tabs)[number][0]>('storage')
const subtabs=[['users','Пользователи'],['requests','Заявки'],['roles','Роли']] as const
const visibleAccountTabs=computed(()=>subtabs.filter(([key])=>session.can(key==='users'?'accounts.view':key==='requests'?'accounts.requests':'accounts.roles')))
const accountTab=ref<'users'|'requests'|'roles'>('users')
watch(visibleTabs,items=>{if(!items.some(([key])=>key===active.value)&&items[0])active.value=items[0][0]},{immediate:true})
watch(visibleAccountTabs,items=>{if(!items.some(([key])=>key===accountTab.value)&&items[0])accountTab.value=items[0][0]},{immediate:true})
const pending=ref<number|null>(null)
async function count(){if(active.value!=='accounts'||!session.can('accounts.requests'))return;try{pending.value=(await accountsApi.registration()).pending}catch{pending.value=null}}
watch(active,()=>void count())
usePolling(count,15000)
</script>

<template>
  <PageHeader eyebrow="УПРАВЛЕНИЕ СИСТЕМОЙ" title="Администрирование"/>
  <div class="settings-layout">
    <nav aria-label="Разделы администрирования" class="admin-nav">
      <button v-for="[key,label] in visibleTabs" :key="key" class="btn small" :class="active===key?'primary':'secondary'" :aria-pressed="active===key" @click="active=key">{{label}}</button>
    </nav>
    <section v-if="active==='storage'||active==='limits'" :aria-label="active==='storage'?'Хранилище':'Лимиты и хранение'" class="stack">
      <StorageCenter :mode="active"/>
    </section>
    <section v-else-if="active==='accounts'" aria-label="Пользователи" class="stack">
      <nav class="admin-nav" aria-label="Разделы аккаунтов">
        <button v-for="item in visibleAccountTabs" :key="item[0]" class="btn small" :class="accountTab===item[0]?'primary':'secondary'" :aria-pressed="accountTab===item[0]" @click="accountTab=item[0]">{{item[1]}}<template v-if="item[0]==='requests'&&pending"> ({{pending}})</template></button>
      </nav>
      <template v-if="accountTab==='users'">
        <AccountDirectory :refresh-key="accountRefresh" @created="requestRefresh++"/>
      </template>
      <template v-else-if="accountTab==='requests'"><RegistrationPanel/><AccessRequests :refresh-key="requestRefresh" @approved="accountRefresh++;count()"/></template>
      <RolesPanel v-else/>
    </section>
    <div v-else class="stack">
      <section v-if="session.can('system.update_status')" aria-label="Обновления" class="stack"><MapUpdater/></section>
      <section v-if="session.can('system.models')||session.can('system.processing_view')" aria-label="MegaLoc" class="stack"><MegaLocSettings/></section>
      <section v-if="session.can('system.performance_view')" aria-label="Производительность" class="stack"><PerformanceSettings/></section>
      <section v-if="session.can('system.status')" aria-label="Система" class="stack"><SystemSettings/></section>
    </div>
  </div>
</template>
<style scoped>.admin-nav{display:flex;flex-wrap:wrap;gap:8px}.admin-nav .btn{white-space:normal}.admin-nav .btn[aria-pressed=true]{font-weight:650}</style>
