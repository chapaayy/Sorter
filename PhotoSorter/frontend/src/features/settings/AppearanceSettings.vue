<script setup lang="ts">
import {useThemeStore} from '../../stores/theme'
import type {ThemeChoice} from '../../types/api'
const theme=useThemeStore()
</script>
<template>
<section class="panel stack">
  <h2>Оформление</h2>
  <p class="meta">Единая монохромная тема для всех карточек, диалогов и галерей.</p>
  <div class="segment" role="radiogroup" aria-label="Тема сайта">
    <button v-for="value in (['system','dark','light'] as ThemeChoice[])" :key="value"
      role="radio" :aria-checked="theme.choice===value"
      :class="{active:theme.choice===value}" @click="theme.choice=value">
      {{value==='system'?'Системная':value==='dark'?'Тёмная':'Светлая'}}
    </button>
  </div>
</section>
</template>
