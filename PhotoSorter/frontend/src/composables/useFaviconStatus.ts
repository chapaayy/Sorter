import {onMounted,onBeforeUnmount,watch} from 'vue'
import {useRoute} from 'vue-router'
import {useSessionStore} from '../stores/session'
import {useUploadCenterStore} from '../stores/uploadCenter'
import {api,ApiError} from '../api/client'
import {FaviconState,idleIcon,combineActivity,type IconState,type OwnWorkStatus} from '../utils/faviconState'
import {FaviconRenderer} from '../utils/faviconRenderer'
import {uploadPercent} from '../utils/transferPresentation'

/** Independent of page polling, including while hidden. Only the authenticated
 * server projection and this tab's uploads can affect the icon. */
export function useFaviconStatus(){
  const session=useSessionStore(),route=useRoute(),upload=useUploadCenterStore()
  let renderer:FaviconRenderer|undefined
  let tracker=new FaviconState(),healthy=false
  let timer:number|undefined,request:AbortController|undefined,generation=0
  let account:string|null=null,permissionKey=''
  let uploadSuccess=false,uploadConfirmation=false,uploadRow:number|undefined
  // Older owner and observer /auth/me responses intentionally omit the ID.
  const eligible=()=>session.checked&&!session.checkFailed&&session.user
    ?session.user.username:null
  const rights=()=>JSON.stringify(Object.entries(session.user?.permissions||{}).sort(([a],[b])=>a.localeCompare(b)))
  function cancel(){
    generation++
    if(timer!==undefined){window.clearTimeout(timer);timer=undefined}
    request?.abort();request=undefined
  }
  function reset(){
    cancel();healthy=false;tracker=new FaviconState();renderer?.reset()
    uploadSuccess=false;uploadConfirmation=false;uploadRow=undefined
  }
  function schedule(delay:number){
    if(timer!==undefined)window.clearTimeout(timer)
    if(account!==null)timer=window.setTimeout(()=>{timer=undefined;void poll()},delay)
  }
  function local():IconState{
    const row=upload.current
    if(!account||eligible()!==account)return idleIcon
    if(row){
      if(row.status==='running')return {kind:'running',run:'upload:'+row.id,progress:row.totalBytes>0?uploadPercent(row)/100:null}
      if(row.status==='failed')return {kind:'error'}
      if(row.status==='waiting')return {kind:'queued'}
      return {kind:'paused'}
    }
    if(uploadConfirmation&&healthy)return {kind:'running',run:'upload-confirmation',progress:null}
    if(uploadSuccess&&healthy&&!uploadConfirmation)return {kind:'success'}
    return idleIcon
  }
  function display(){renderer?.set(combineActivity(healthy?tracker.state():idleIcon,local()))}
  async function poll(){
    if(account===null||request)return
    const id=account,epoch=generation,controller=new AbortController()
    request=controller
    const confirmationAtStart=uploadConfirmation
    const timeout=window.setTimeout(()=>controller.abort(),10000)
    try{
      const snapshot=await api<OwnWorkStatus>('/activity/own',{signal:controller.signal})
      if(epoch!==generation||eligible()!==id)return
      if(snapshot.username!==id||(session.user?.id!=null&&String(snapshot.account_id)!==String(session.user.id))||!Array.isArray(snapshot.tasks))throw Error('Invalid personal status')
      tracker.update(snapshot);healthy=true
      if(confirmationAtStart)uploadConfirmation=false
      display()
    }catch(error){
      if(epoch!==generation||eligible()!==id)return
      healthy=false
      if(error instanceof ApiError&&(error.status===401||error.status===403)){
        tracker=new FaviconState();uploadSuccess=false;uploadConfirmation=false;renderer?.reset()
      }else display()
    }finally{
      window.clearTimeout(timeout)
      if(epoch===generation){
        request=undefined
        const state=tracker.state()
        schedule(uploadConfirmation?1000:healthy&&state.kind==='running'?2000:5000)
      }
    }
  }
  function refresh(){
    if(account===null||request)return
    if(timer!==undefined){window.clearTimeout(timer);timer=undefined}
    void poll()
  }
  function changeAccount(){
    const next=eligible(),nextRights=rights()
    if(next===account&&nextRights===permissionKey)return
    const switched=next!==account
    reset();account=next;permissionKey=nextRights
    if(switched)upload.reset()
    if(account!==null)void poll()
  }
  function visible(){
    if(document.hidden||account===null)return
    tracker.acknowledgeSuccess();uploadSuccess=false;display();refresh()
  }
  function visited(){
    if(document.hidden)return
    if(route.path.startsWith('/queue/runs/'))tracker.acknowledgeRun(route.path.split('/')[3]||'')
    else if(route.path==='/results'||route.path.startsWith('/results/'))tracker.acknowledgeSuccess()
    display()
  }
  function historyViewed(event:Event){
    if(account===null||document.hidden)return
    const runs=(event as CustomEvent<unknown>).detail
    if(Array.isArray(runs))for(const run of runs)if(typeof run==='string')tracker.acknowledgeRun(run)
    display()
  }
  watch([eligible,rights],()=>{if(renderer)changeAccount()},{flush:'sync'})
  watch(()=>route.fullPath,visited)
  watch(()=>upload.lastCompleted,(value)=>{
    if(!account||!value)return
    uploadSuccess=true;uploadConfirmation=true;display();refresh()
  })
  watch(()=>[upload.current?.id,upload.current?.status,upload.current?.sentBytes,upload.current?.totalBytes],()=>{
    if(upload.current&&uploadRow!==upload.current.id){
      uploadRow=upload.current.id;uploadSuccess=false;uploadConfirmation=false
    }
    display()
  })
  onMounted(()=>{
    renderer=new FaviconRenderer()
    document.addEventListener('visibilitychange',visible)
    window.addEventListener('map:queue-history-viewed',historyViewed)
    changeAccount()
  })
  onBeforeUnmount(()=>{
    cancel();account=null;renderer?.dispose();renderer=undefined
    document.removeEventListener('visibilitychange',visible)
    window.removeEventListener('map:queue-history-viewed',historyViewed)
  })
}
