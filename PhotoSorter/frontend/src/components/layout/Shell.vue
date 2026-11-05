<script setup lang="ts">
import {ref,watch} from 'vue'
import {useRoute,RouterLink} from 'vue-router'
import {useSessionStore} from '../../stores/session'
const menu=ref(false),route=useRoute(),session=useSessionStore()
watch(()=>route.path,()=>{menu.value=false})
const links=[
{to:'/fo',label:'ФО',icon:'▤'},
{to:'/references',label:'Образцы',icon:'▦'},
{to:'/processing',label:'Обработка',icon:'◉'},
{to:'/results',label:'Результаты',icon:'▣'},
{to:'/logs',label:'Логи',icon:'⌘'},
{to:'/settings',label:'Настройки',icon:'⚙'}
]
const title=()=>links.find(l=>route.path.startsWith(l.to))?.label||'Фотоотчёты'
</script>
<template>
  <div class="app-shell">
    <div v-if="menu" class="drawer-backdrop" @click="menu=false" aria-hidden="true"></div>
    <aside class="sidebar" :class="{open:menu}" aria-label="Основное меню">
      <RouterLink class="brand" to="/fo" @click="menu=false">
        <div class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
        <div><strong>OUTDOOR</strong><small>PHOTO SORTER</small></div>
      </RouterLink>
      <div class="nav-caption">РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav class="nav-links">
        <RouterLink v-for="link in links.slice(0,5)" :key="link.to" :to="link.to" class="nav-link">
          <span class="nav-icon" aria-hidden="true">{{link.icon}}</span>{{link.label}}
        </RouterLink>
      </nav>
      <div class="sidebar-bottom">
        <div class="nav-links"><RouterLink to="/settings" class="nav-link"><span class="nav-icon">⚙</span>Настройки</RouterLink></div>
        <div class="server-pill">Приватная панель · MegaLoc</div>
      </div>
    </aside>
    <section class="main-area">
      <header class="main-header">
        <div class="mobile-top"><button class="btn ghost icon" aria-label="Открыть меню" @click="menu=true">☰</button><strong>OUTDOOR</strong></div>
        <div class="breadcrumbs desktop-only">Приложение <span>›</span> <b>{{title()}}</b></div>
        <div class="header-right"><span class="desktop-only">{{session.user?.username}}</span><button class="btn ghost small" @click="session.logout()">Выйти</button></div>
      </header>
      <main class="content"><slot/></main>
    </section>
  </div>
</template>
