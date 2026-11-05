import {onMounted,onUnmounted,ref} from 'vue'
export function usePolling(fn:()=>Promise<unknown>,interval=5000){
  const busy=ref(false)
  let timer:ReturnType<typeof setInterval>|undefined
  async function refresh(){
    if(busy.value||document.hidden)return
    busy.value=true
    try{await fn()}finally{busy.value=false}
  }
  onMounted(()=>{timer=setInterval(()=>{void refresh().catch(console.error)},interval)})
  onUnmounted(()=>{if(timer)clearInterval(timer)})
  return {busy,refresh}
}
