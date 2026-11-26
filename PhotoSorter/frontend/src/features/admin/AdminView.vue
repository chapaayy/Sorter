<script setup lang="ts">
import {ref} from 'vue'
import PageHeader from '../../components/ui/PageHeader.vue'
import Accounts from './users/Accounts.vue'
import AccessRequests from './users/AccessRequests.vue'
import StorageCenter from './storage/StorageCenter.vue'
import StorageAccounts from './storage/StorageAccounts.vue'
import MapUpdater from './MapUpdater.vue'
import MegaLocSettings from '../settings/MegaLocSettings.vue'
import PerformanceSettings from '../settings/PerformanceSettings.vue'
import SystemSettings from '../settings/SystemSettings.vue'

const accountRefresh=ref(0),requestRefresh=ref(0)
const tabs=[['storage','Хранилище'],['accounts','Аккаунты'],['limits','Лимиты и хранение'],['system','Система']] as const
const active=ref<(typeof tabs)[number][0]>('storage')
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
      <Accounts :refresh-key="accountRefresh" @created="requestRefresh++"/>
      <AccessRequests :refresh-key="requestRefresh" @approved="accountRefresh++"/>
      <StorageAccounts/>
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
