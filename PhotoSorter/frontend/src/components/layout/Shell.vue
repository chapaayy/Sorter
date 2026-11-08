<script setup lang="ts">
import {ref,watch} from 'vue'
import {useRoute,RouterLink} from 'vue-router'
import {useSessionStore} from '../../stores/session'
import {useSidebarStore} from '../../stores/sidebar'
import UiIcon from '../ui/UiIcon.vue'
import UploadCenter from '../upload/UploadCenter.vue'

const menu=ref(false),route=useRoute(),session=useSessionStore(),sidebar=useSidebarStore()
watch(()=>route.path,()=>{menu.value=false})
const links=[
  {to:'/fo',label:'Фотографии',icon:'photos'},
  {to:'/references',label:'Образцы',icon:'references'},
  {to:'/layouts',label:'Макеты рекламы',icon:'layouts'},
  {to:'/queue',label:'Очередь',icon:'queue'},
  {to:'/results',label:'Результаты',icon:'results'},
  {to:'/logs',label:'Логи',icon:'logs'},
  {to:'/settings',label:'Настройки',icon:'settings'}
] as const
const title=()=>links.find(link=>route.path.startsWith(link.to))?.label||'Фотоотчёты'
</script>

<template>
  <div class="app-shell" :class="{'is-sidebar-collapsed':sidebar.collapsed}">
    <div v-if="menu" class="drawer-backdrop" @click="menu=false" aria-hidden="true"></div>
    <aside class="sidebar" :class="{open:menu}" aria-label="Основное меню">
      <div class="sidebar-brand-row">
        <RouterLink class="brand" to="/fo" aria-label="OUTDOOR PhotoSorter — Фотографии" @click="menu=false">
          <div class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
          <div class="brand-text"><strong>OUTDOOR</strong><small>PHOTO SORTER</small></div>
        </RouterLink>
        <button class="sidebar-toggle" type="button"
          :aria-label="sidebar.collapsed?'Развернуть боковое меню':'Свернуть боковое меню'"
          :title="sidebar.collapsed?'Развернуть меню':'Оставить только иконки'"
          @click="sidebar.toggle()">
          <UiIcon :name="sidebar.collapsed?'sidebar-expand':'sidebar-collapse'" :size="18"/>
        </button>
      </div>
      <div class="nav-caption">РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav class="nav-links" aria-label="Разделы">
        <RouterLink v-for="link in links.filter(item=>item.to!=='/settings')" :key="link.to" :to="link.to"
          class="nav-link" :aria-label="link.label"
          :title="sidebar.collapsed?link.label:undefined">
          <span class="nav-icon" aria-hidden="true"><UiIcon :name="link.icon"/></span>
          <span class="nav-text">{{link.label}}</span>
        </RouterLink>
      </nav>
      <div class="sidebar-bottom">
        <nav class="nav-links" aria-label="Настройки">
          <RouterLink to="/settings" class="nav-link" aria-label="Настройки"
            :title="sidebar.collapsed?'Настройки':undefined">
            <span class="nav-icon" aria-hidden="true"><UiIcon name="settings"/></span>
            <span class="nav-text">Настройки</span>
          </RouterLink>
        </nav>
        <div class="server-pill" title="Приватная панель · MegaLoc">
          <span class="server-pill-text">Приватная панель · MegaLoc</span>
        </div>
      </div>
    </aside>
    <section class="main-area" :class="{'reference-layout':route.name==='references'}">
      <header class="main-header">
        <div class="mobile-top">
          <button class="btn ghost icon" aria-label="Открыть меню" @click="menu=true">
            <UiIcon name="menu"/>
          </button>
          <strong>OUTDOOR</strong>
        </div>
        <div class="breadcrumbs desktop-only">Приложение <span>›</span> <b>{{title()}}</b></div>
        <div class="header-right">
          <span class="desktop-only">{{session.user?.username}}</span>
          <button class="btn ghost small" @click="session.logout()">Выйти</button>
        </div>
      </header>
      <main class="content"><slot/></main>
    </section>
    <UploadCenter/>
  </div>
</template>
