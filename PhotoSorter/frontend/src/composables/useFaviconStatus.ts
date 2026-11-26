import {onMounted,onBeforeUnmount,watch} from 'vue'
import {useRoute} from 'vue-router'
import {useSessionStore} from '../stores/session'
import {api,ApiError} from '../api/client'
import {FaviconState,idleIcon,type OwnWorkStatus} from '../utils/faviconState'
import {FaviconRenderer} from '../utils/faviconRenderer'

/** The tab is independent from route polling, including while hidden. */
export function useFaviconStatus(){
  const session=useSessionStore(),route=useRoute()
  let renderer:FaviconRenderer|undefined
  let tracker=new FaviconState(),healthy=false
  let timer:number|undefined,request:AbortController|undefined,generation=0
  let account:string|null=null
  const eligible=()=>session.checked&&!session.checkFailed&&session.user?.id!=null&&session.can('queue.view')
    ?String(session.user.id):null
  function cancel(){
    generation++
    if(timer!==undefined){window.clearTimeout(timer);timer=undefined}
    request?.abort();request=undefined
  }
  function reset(){
    cancel();healthy=false;tracker=new FaviconState();renderer?.reset()
  }
  function schedule(delay:number){
    if(timer!==undefined)window.clearTimeout(timer)
    if(account!==null)timer=window.setTimeout(()=>{timer=undefined;void poll()},delay)
  }
  function display(){renderer?.set(healthy?tracker.state():idleIcon)}
  async function poll(){
    if(account===null||request)return
    const id=account,epoch=generation,controller=new AbortController()
    request=controller
    // A dead or suspended connection must not leave a poll permanently stuck.
    const timeout=window.setTimeout(()=>controller.abort(),10000)
    try{
      const snapshot=await api<OwnWorkStatus>('/work-queue/own-status',{signal:controller.signal})
      if(epoch!==generation||eligible()!==id)return
      if(String(snapshot.account_id)!==id||!Array.isArray(snapshot.tasks))throw Error('Invalid personal status')
      tracker.update(snapshot);healthy=true;display()
    }catch(error){
      if(epoch!==generation||eligible()!==id)return
      healthy=false
      if(error instanceof ApiError&&(error.status===401||error.status===403)){tracker=new FaviconState();renderer?.reset()}
      else display()
    }finally{
      window.clearTimeout(timeout)
      if(epoch===generation){
        request=undefined
        const state=tracker.state()
        schedule(healthy&&state.kind==='running'?2000:5000)
      }
    }
  }
  function changeAccount(){
    const next=eligible()
    if(next===account)return
    reset();account=next
    if(account!==null)void poll()
  }
  function visible(){
    if(document.hidden||account===null)return
    tracker.acknowledgeSuccess();display()
    if(!request){if(timer!==undefined){window.clearTimeout(timer);timer=undefined}void poll()}
  }
  function visited(){
    if(route.path==='/queue'&&route.query.view==='history')tracker.acknowledgeHistory()
    else if(route.path.startsWith('/queue/runs/'))tracker.acknowledgeRun(route.path.split('/')[3]||'')
    else if(route.path==='/results'||route.path.startsWith('/results/'))tracker.acknowledgeSuccess()
    display()
  }
  watch(eligible,()=>{if(renderer)changeAccount()},{flush:'sync'})
  watch(()=>route.fullPath,visited)
  onMounted(()=>{
    renderer=new FaviconRenderer()
    document.addEventListener('visibilitychange',visible)
    changeAccount()
  })
  onBeforeUnmount(()=>{
    cancel();account=null;renderer?.dispose();renderer=undefined
    document.removeEventListener('visibilitychange',visible)
  })
}
