import {defineStore} from 'pinia'
import {computed,ref,shallowRef} from 'vue'
import {createFoTransfer,transferRecovery} from '../utils/foTransfer'
import {transferReferences} from '../utils/referenceTransfer'
import {errorText} from '../utils/format'
import {useNoticeStore} from './notice'
import {useUploadSettingsStore} from './uploadSettings'
import type {RecoverySource,UploadCompletion,UploadContext,UploadResult,UploadRow,UploadSource} from '../types/uploadQueue'

type Form={mode:'fo'|'construction'|'single';id:number;sam:string;samLabel:string}
type Runner=(context:UploadContext)=>Promise<UploadResult>

/** One transfer at a time per tab, with no connection to the MegaLoc scheduler. */
export const useUploadCenterStore=defineStore('upload-center',()=>{
  const form=shallowRef<Form|null>(null),queueOpen=ref(false),rows=ref<UploadRow[]>([])
  const current=computed(()=>rows.value[0])
  const lastCompleted=shallowRef<UploadCompletion|null>(null)
  const notice=useNoticeStore(),settings=useUploadSettingsStore()
  const runners=new Map<number,Runner>()
  let serial=0
  let attempt:{id:number;controller:AbortController;cancelled:boolean}|null=null

  function launch(mode:Form['mode'],sam='',samLabel=''){
    queueOpen.value=false
    form.value={mode,sam,samLabel,id:++serial}
  }
  function closeForm(){form.value=null}
  function showQueue(){closeForm();queueOpen.value=true}
  function closeQueue(){queueOpen.value=false}
  function isBatchScheduled(id:string){
    return rows.value.some(row=>row.batchId===id)
  }
  function complete(completion:UploadCompletion){lastCompleted.value=completion}
  function enqueue(source:UploadSource){
    if(source.kind==='recovery'&&isBatchScheduled(source.source.batchId)){
      showQueue()
      return
    }
    const id=++serial
    const base={id,status:'waiting' as const,error:'',phase:'',completed:0,sentBytes:0}
    let row:UploadRow
    if(source.kind==='fo'){
      const totalBytes=source.entries.reduce((sum,e)=>sum+e.file.size,0)
      row={...base,kind:'fo',name:source.name,totalBytes,totalFiles:source.entries.length}
      runners.set(id,createFoTransfer(source))
    }else if(source.kind==='references'){
      row={...base,kind:'references',name:source.name,totalBytes:source.review.totalBytes,totalFiles:source.review.newFiles.length}
      runners.set(id,context=>transferReferences(source.review,source.success,context))
    }else{
      row={...base,kind:'fo',name:source.source.item.filename,totalBytes:source.source.item.size,
        sentBytes:source.source.item.received,totalFiles:1,batchId:source.source.batchId,recovery:true}
      runners.set(id,context=>transferRecovery(source.source,context))
    }
    const waits=!!current.value
    rows.value.push(row)
    closeForm()
    if(waits)notice.add('Добавлено в очередь загрузок: '+row.name,'info')
    void runNext()
  }
  function resume(source:RecoverySource){enqueue({kind:'recovery',source})}
  function discard(id:number){
    rows.value=rows.value.filter(row=>row.id!==id)
    runners.delete(id)
  }
  async function runNext(){
    const row=current.value
    if(attempt||!row||row.status!=='waiting')return
    const run=runners.get(row.id)
    if(!run)return
    const active={id:row.id,controller:new AbortController(),cancelled:false}
    attempt=active
    row.status='running';row.error=''
    try{
      const result=await run({
        signal:active.controller.signal,parallel:settings.parallelUploads,
        report:progress=>{if(attempt===active&&!active.controller.signal.aborted)Object.assign(row,progress)},
        setBatch:id=>{if(attempt===active)row.batchId=id}
      })
      if(attempt!==active||active.cancelled)return
      discard(row.id)
      if(result.completion)complete(result.completion)
      notice.add(result.message,result.completion?'ok':'info',result.action)
    }catch(e){
      if(attempt!==active||active.cancelled)return
      row.status=active.controller.signal.aborted?'paused':'failed'
      if(row.status==='failed')row.error=errorText(e)
    }finally{
      if(attempt===active){
        attempt=null
        if(active.cancelled)discard(row.id)
        void runNext()
      }
    }
  }
  function pause(id:number){
    const row=current.value
    if(!row||row.id!==id||row.status!=='running'||attempt?.id!==id)return
    row.status='pausing'
    attempt.controller.abort()
  }
  function continueUpload(id:number){
    const row=current.value
    if(!row||row.id!==id||!['paused','failed'].includes(row.status))return
    row.status='waiting'
    void runNext()
  }
  function cancel(id:number){
    const row=rows.value.find(row=>row.id===id)
    if(!row)return
    if(attempt?.id===id){
      attempt.cancelled=true
      row.status='cancelling'
      attempt.controller.abort()
    }else{
      discard(id)
      void runNext()
    }
  }
  function reset(){
    const active=attempt
    attempt=null
    active?.controller.abort()
    runners.clear()
    rows.value=[];form.value=null;queueOpen.value=false;lastCompleted.value=null
  }
  return {form,queueOpen,rows,current,lastCompleted,launch,closeForm,showQueue,closeQueue,complete,
    enqueue,resume,isBatchScheduled,pause,continueUpload,cancel,reset}
})
