<script setup lang="ts">
import {ref} from 'vue'
import PageHeader from '../../components/ui/PageHeader.vue'
import AppearanceSettings from './AppearanceSettings.vue'
import UploadSettings from './UploadSettings.vue'
import MegaLocSettings from './MegaLocSettings.vue'
import StorageSettings from './StorageSettings.vue'
import SystemSettings from './SystemSettings.vue'
type Category='appearance'|'uploads'|'megaloc'|'storage'|'system'
const selected=ref<Category>('appearance')
const sections:Array<{id:Category;name:string;detail:string}>=[
  {id:'appearance',name:'Оформление',detail:'Тёмная и светлая темы'},
  {id:'uploads',name:'Загрузка файлов',detail:'Потоки, докачка'},
  {id:'megaloc',name:'MegaLoc и CPU',detail:'Параметры обработки'},
  {id:'storage',name:'Хранилище',detail:'Место и очистка'},
  {id:'system',name:'Система',detail:'Сервисы и диагностика'}
]
</script>
<template>
<PageHeader eyebrow="ПАРАМЕТРЫ" title="Настройки"
  subtitle="Управление обработкой, загрузками, хранилищем и интерфейсом."/>
<div class="settings-layout">
  <nav class="panel settings-categories" aria-label="Категории настроек">
    <button v-for="item in sections" :key="item.id" type="button"
      :class="{active:selected===item.id}" :aria-current="selected===item.id?'page':undefined"
      @click="selected=item.id">
      <strong>{{item.name}}</strong><span>{{item.detail}}</span>
    </button>
  </nav>
  <div class="settings-detail">
    <AppearanceSettings v-if="selected==='appearance'"/>
    <UploadSettings v-else-if="selected==='uploads'"/>
    <MegaLocSettings v-else-if="selected==='megaloc'"/>
    <StorageSettings v-else-if="selected==='storage'"/>
    <SystemSettings v-else/>
  </div>
</div>
</template>
