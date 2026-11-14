<script setup lang="ts">
import type {ThemeChoice} from '../../types/api'

defineProps<{theme:ThemeChoice}>()
</script>

<template>
  <span class="theme-preview" aria-hidden="true">
    <span v-for="palette in (theme==='system'?['light','dark']:[theme])" :key="palette"
      :data-theme="palette" class="theme-preview-palette"
      :class="theme==='system'?'theme-preview-half theme-preview-'+palette:''">
      <span class="theme-preview-window">
        <span class="theme-preview-sidebar">
          <span class="theme-preview-brand">MAP</span>
          <i class="theme-preview-selected"/><i/><i/>
        </span>
        <span class="theme-preview-content">
          <span class="theme-preview-topbar"/>
          <span class="theme-preview-title"/>
          <span v-for="n in 2" :key="n" class="theme-preview-report">
            <span class="theme-preview-photo"/><span class="theme-preview-lines"><i/><i/></span>
          </span>
        </span>
      </span>
    </span>
  </span>
</template>
