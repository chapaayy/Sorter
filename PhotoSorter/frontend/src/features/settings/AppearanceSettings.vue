<script setup lang="ts">
import {useThemeStore} from '../../stores/theme'
import type {ThemeChoice} from '../../types/api'
import ThemePreview from './ThemePreview.vue'

const theme=useThemeStore()
const options:{value:ThemeChoice;label:string;description?:string}[]=[
  {value:'system',label:'Системная',description:'Как на устройстве'},
  {value:'dark',label:'Тёмная'},
  {value:'light',label:'Светлая'}
]
</script>

<template>
  <section class="panel stack" aria-labelledby="appearance-heading">
    <h2 id="appearance-heading">Оформление</h2>
    <div class="theme-options" role="radiogroup" aria-label="Тема сайта">
      <label v-for="option in options" :key="option.value" class="theme-option">
        <input v-model="theme.choice" class="visually-hidden" type="radio" name="map-theme"
          :value="option.value" :aria-labelledby="'theme-label-'+option.value"
          :aria-describedby="option.description?'theme-description-'+option.value:undefined"/>
        <span class="theme-option-card">
          <ThemePreview :theme="option.value"/>
          <span class="theme-option-title">
            <strong :id="'theme-label-'+option.value">{{option.label}}</strong>
            <span v-if="theme.choice===option.value" class="theme-option-check" aria-hidden="true">✓</span>
          </span>
          <span v-if="option.description" :id="'theme-description-'+option.value" class="meta">{{option.description}}</span>
        </span>
      </label>
    </div>
  </section>
</template>
