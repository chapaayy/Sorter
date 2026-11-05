<script setup lang="ts">
import {ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {useSessionStore} from '../../stores/session'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
const username=ref('admin'),password=ref(''),busy=ref(false),error=ref('')
const session=useSessionStore(),router=useRouter(),route=useRoute()
async function submit(){
  busy.value=true;error.value=''
  try{
    await session.login(username.value,password.value)
    const next=typeof route.query.next==='string'&&route.query.next.startsWith('/')&&!route.query.next.startsWith('//')?route.query.next:'/fo'
    await router.replace(next)
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
  <div class="login-page"><form class="login-card stack" @submit.prevent="submit">
    <div class="brand"><div class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></div><div><strong>OUTDOOR</strong><small>PHOTO SORTER</small></div></div>
    <div><div class="eyebrow">ПРИВАТНАЯ ПАНЕЛЬ</div><h1 style="margin:8px 0">С возвращением</h1><p class="muted">Войдите, чтобы работать с фотоотчётами.</p></div>
    <div class="field"><label for="user">Логин</label><input id="user" v-model="username" autocomplete="username" required maxlength="64" /></div>
    <div class="field"><label for="pass">Пароль</label><input id="pass" v-model="password" type="password" autocomplete="current-password" required /></div>
    <div v-if="error" class="alert error" role="alert">{{error}}</div>
    <UiButton kind="primary" type="submit" :loading="busy">Войти в панель</UiButton>
  </form></div>
</template>
