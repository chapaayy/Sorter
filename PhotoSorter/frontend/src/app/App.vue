<script setup lang="ts">
import {onMounted,watch} from 'vue'
import {useRoute,useRouter,RouterView} from 'vue-router'
import {useSessionStore} from '../stores/session'
import {useThemeStore} from '../stores/theme'
import Shell from '../components/layout/Shell.vue'
import ToastStack from '../components/ui/ToastStack.vue'
const session=useSessionStore()
useThemeStore()
const route=useRoute(),router=useRouter()
async function gate(){
  if(!session.checked)return
  if(!session.user && !route.meta.public)await router.replace({name:'login',query:{next:route.fullPath}})
  if(session.user && (route.meta.public || (!session.isOwner && !route.meta.viewer)))await router.replace(session.home)
}
onMounted(async()=>{await session.check();await gate()})
watch(()=>route.fullPath,()=>{void gate()})
</script>
<template>
  <div v-if="!session.checked" class="auth-loading">MAP</div>
  <RouterView v-else-if="route.meta.public"/>
  <Shell v-else-if="session.user&&(session.isOwner||route.meta.viewer)"><RouterView/></Shell>
  <ToastStack/>
</template>
