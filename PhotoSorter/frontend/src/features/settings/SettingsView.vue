<script setup lang="ts">
import {ref} from 'vue'
import PageHeader from '../../components/ui/PageHeader.vue'
import AppearanceSettings from './AppearanceSettings.vue'
import UploadSettings from './UploadSettings.vue'
import MegaLocSettings from './MegaLocSettings.vue'
import PerformanceSettings from './PerformanceSettings.vue'
import StorageSettings from './StorageSettings.vue'
import SystemSettings from './SystemSettings.vue'
import AccessRequests from './users/AccessRequests.vue'
type Category='appearance'|'uploads'|'megaloc'|'performance'|'storage'|'system'|'users'
const selected=ref<Category>('appearance')
const sections:Array<{id:Category;name:string;detail:string}>=[
  {id:'appearance',name:'Оформление',detail:'Тёмная и светлая темы'},
  {id:'uploads',name:'Загрузка файлов',detail:'Потоки, докачка'},
  {id:'megaloc',name:'MegaLoc',detail:'Параметры группировки'},
  {id:'performance',name:'Производительность',detail:'CPU и службы'},
  {id:'storage',name:'Хранилище',detail:'Место и очистка'},
  {id:'system',name:'Система',detail:'Сервисы и диагностика'},
  {id:'users',name:'Пользователи',detail:'Заявки на доступ'}
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
    <PerformanceSettings v-else-if="selected==='performance'"/>
    <StorageSettings v-else-if="selected==='storage'"/>
    <SystemSettings v-else-if="selected==='system'"/>
    <AccessRequests v-else/>
  </div>
</div>
</template>
