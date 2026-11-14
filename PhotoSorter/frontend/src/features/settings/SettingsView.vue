<script setup lang="ts">
import PageHeader from '../../components/ui/PageHeader.vue'
import AppearanceSettings from './AppearanceSettings.vue'
import UploadSettings from './UploadSettings.vue'
import MegaLocSettings from './MegaLocSettings.vue'
import PerformanceSettings from './PerformanceSettings.vue'
import StorageSettings from './StorageSettings.vue'
import SystemSettings from './SystemSettings.vue'
import AccessRequests from './users/AccessRequests.vue'
import AboutSettings from './AboutSettings.vue'
</script>

<template>
  <PageHeader eyebrow="ПАРАМЕТРЫ" title="Настройки"/>
  <div class="settings-layout">
    <AppearanceSettings/>
    <UploadSettings/>
    <section aria-label="MegaLoc"><MegaLocSettings/></section>
    <section aria-label="Производительность"><PerformanceSettings/></section>
    <section aria-label="Хранилище"><StorageSettings/></section>
    <section aria-label="Система"><SystemSettings/></section>
    <section aria-label="Пользователи"><AccessRequests/></section>
    <AboutSettings/>
  </div>
</template>
