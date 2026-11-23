<script setup lang="ts">
import {ref} from 'vue'
import PageHeader from '../../components/ui/PageHeader.vue'
import Accounts from './users/Accounts.vue'
import AccessRequests from './users/AccessRequests.vue'
import StorageInventory from './StorageInventory.vue'
import HostAudit from './HostAudit.vue'
import MegaLocSettings from '../settings/MegaLocSettings.vue'
import PerformanceSettings from '../settings/PerformanceSettings.vue'
import StorageSettings from '../settings/StorageSettings.vue'
import SystemSettings from '../settings/SystemSettings.vue'

const accountRefresh=ref(0),requestRefresh=ref(0)
</script>

<template>
  <PageHeader eyebrow="УПРАВЛЕНИЕ СИСТЕМОЙ" title="Администрирование"/>
  <div class="settings-layout">
    <section aria-label="Пользователи" class="stack">
      <Accounts :refresh-key="accountRefresh" @created="requestRefresh++"/>
      <AccessRequests :refresh-key="requestRefresh" @approved="accountRefresh++"/>
    </section>
    <section aria-label="MegaLoc" class="stack"><MegaLocSettings/></section>
    <section aria-label="Производительность" class="stack"><PerformanceSettings/></section>
    <section aria-label="Реестр файлов" class="stack"><StorageInventory/></section>
    <section aria-label="Аудит сервера" class="stack"><HostAudit/></section>
    <section aria-label="Хранилище" class="stack"><StorageSettings/></section>
    <section aria-label="Система" class="stack"><SystemSettings/></section>
  </div>
</template>
