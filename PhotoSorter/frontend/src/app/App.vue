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
  if(!session.user && route.name!=='login')await router.replace({name:'login',query:{next:route.fullPath}})
  if(session.user && route.name==='login')await router.replace('/fo')
}
onMounted(async()=>{await session.check();await gate()})
watch(()=>route.fullPath,()=>{void gate()})
</script>
<template>
  <div v-if="!session.checked" class="login-page"><div class="eyebrow">OUTDOOR · PHOTOSORTER</div></div>
  <RouterView v-else-if="route.name==='login'"/>
  <Shell v-else-if="session.user"><RouterView/></Shell>
  <ToastStack/>
</template>
