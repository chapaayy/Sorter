<script setup lang="ts">
import {onMounted,watch} from 'vue'
import {useRoute,useRouter,RouterView} from 'vue-router'
import {useSessionStore} from '../stores/session'
import {useThemeStore} from '../stores/theme'
import Shell from '../components/layout/Shell.vue'
import UiButton from '../components/ui/UiButton.vue'
import ToastStack from '../components/ui/ToastStack.vue'
import {usePolling} from '../composables/usePolling'
import {useFaviconStatus} from '../composables/useFaviconStatus'
const session=useSessionStore()
useThemeStore()
const route=useRoute(),router=useRouter()
async function gate(){
  if(!session.checked)return
  if(!session.user && !route.meta.public)await router.replace({name:'login',query:{next:route.fullPath}})
  if(session.user && (route.meta.public || !session.canPath(route.path)))await router.replace(session.home)
}
async function restoreSession(){await session.check();await gate()}
onMounted(restoreSession)
watch(()=>route.fullPath,()=>{void gate()})
watch(()=>session.user?.permissions,()=>{void gate()})
usePolling(session.refreshPermissions,15000)
useFaviconStatus()
</script>
<template>
  <main v-if="session.checkFailed" class="auth-loading">
    <div class="stack">
      <p role="alert">Не удалось проверить сессию. Проверьте соединение и повторите попытку.</p>
      <UiButton kind="primary" @click="restoreSession">Повторить</UiButton>
    </div>
  </main>
  <div v-else-if="!session.checked" class="auth-loading" role="status" aria-label="Проверяем сессию">MAP</div>
  <RouterView v-else-if="route.meta.public&&!session.user"/>
  <Shell v-else-if="!route.meta.public&&session.user&&session.canPath(route.path)"><RouterView/></Shell>
  <ToastStack/>
</template>
