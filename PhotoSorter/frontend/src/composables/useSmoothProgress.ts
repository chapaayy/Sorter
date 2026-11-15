import {onMounted,onScopeDispose,ref,watch} from 'vue'

const TRANSITION_MS=800

/** Animate only between already observed values of the same running task. */
export function useSmoothProgress(target:()=>number|null,key:()=>string|null){
  const shown=ref(target())
  let frame:number|undefined,motion:MediaQueryList|undefined
  function stop(){
    if(frame!==undefined){cancelAnimationFrame(frame);frame=undefined}
  }
  function motionChanged(){
    if(motion?.matches){stop();shown.value=target()}
  }
  onMounted(()=>{
    motion=window.matchMedia('(prefers-reduced-motion: reduce)')
    motion.addEventListener('change',motionChanged)
  })
  onScopeDispose(()=>{
    stop()
    motion?.removeEventListener('change',motionChanged)
  })
  watch([target,key],([next,task],[previous,oldTask])=>{
    stop()
    const from=shown.value
    if(!task||task!==oldTask||motion?.matches||from===null||next===null||
      previous===null||next<=previous||next<=from){
      shown.value=next
      return
    }
    const started=performance.now()
    const step=(now:number)=>{
      const t=Math.max(0,Math.min(1,(now-started)/TRANSITION_MS))
      shown.value=t===1?next:from+(next-from)*t
      frame=t<1?requestAnimationFrame(step):undefined
    }
    frame=requestAnimationFrame(step)
  })
  return shown
}
