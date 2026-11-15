import {onMounted,onUnmounted,ref,watch} from 'vue'
export function usePolling(fn:()=>Promise<unknown>,interval:number|(()=>number)=5000){
  const busy=ref(false)
  let timer:ReturnType<typeof setInterval>|undefined
  async function refresh(){
    if(busy.value||document.hidden)return
    busy.value=true
    try{await fn()}finally{busy.value=false}
  }
  const delay=()=>typeof interval==='number'?interval:interval()
  function reset(){
    if(timer!==undefined)clearInterval(timer)
    timer=setInterval(()=>{void refresh().catch(console.error)},delay())
  }
  onMounted(reset)
  watch(delay,()=>{if(timer!==undefined)reset()})
  onUnmounted(()=>{if(timer)clearInterval(timer)})
  return {busy,refresh}
}
