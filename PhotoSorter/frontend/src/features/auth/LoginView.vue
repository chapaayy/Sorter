<script setup lang="ts">
import {ref} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {useSessionStore} from '../../stores/session'
import {errorText} from '../../utils/format'
import AuthLayout from './AuthLayout.vue'
import AuthField from './AuthField.vue'
const username=ref(''),password=ref(''),busy=ref(false),error=ref('')
const session=useSessionStore(),router=useRouter(),route=useRoute()
async function submit(){
  if(busy.value)return
  busy.value=true;error.value=''
  try{
    // Capture the intended destination before changing reactive session state.
    const next=route.query.next
    await session.login(username.value,password.value)
    const target=typeof next==='string'&&next.startsWith('/')&&!next.startsWith('//')&&!next.includes('\\')?router.resolve(next):null
    const allowed=target&&target.matched.length&&!target.meta.public&&target.name&&(session.isOwner||target.meta.viewer)
    await router.replace(allowed?target.fullPath:session.home)
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
  <AuthLayout title="Войти в MAP" subtitle="Войдите, чтобы работать с фотоотчётами и скачивать готовые результаты.">
    <form class="auth-form" @submit.prevent="submit">
      <AuthField v-model="username" label="Электронная почта или логин" autocomplete="username" :max="254"/>
      <AuthField v-model="password" label="Пароль" type="password" autocomplete="current-password"/>
      <p v-if="error" class="auth-feedback" role="alert">{{error}}</p>
      <button type="submit" class="auth-button primary" :disabled="busy" :aria-busy="busy||undefined" :aria-label="busy?'Входим…':undefined">
        <span v-if="busy" class="btn-spinner" aria-hidden="true"></span>
        <template v-else>Продолжить</template>
      </button>
    </form>
    <div class="auth-divider">ИЛИ</div>
    <RouterLink class="auth-button" :to="{name:'register'}">Зарегистрироваться</RouterLink>
  </AuthLayout>
</template>
