<script setup lang="ts">
import PageHeader from '../../components/ui/PageHeader.vue'
import AppearanceSettings from './AppearanceSettings.vue'
import UploadSettings from './UploadSettings.vue'
import AboutSettings from './AboutSettings.vue'
import FaviconTestSettings from './FaviconTestSettings.vue'
</script>

<template>
  <PageHeader eyebrow="ЛИЧНЫЕ ПАРАМЕТРЫ" title="Настройки"/>
  <div class="settings-layout">
    <AppearanceSettings/>
    <UploadSettings/>
    <FaviconTestSettings/>
    <AboutSettings/>
  </div>
</template>
