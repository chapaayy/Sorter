import {defineStore} from 'pinia'
import {ref,shallowRef} from 'vue'
import type {PendingUpload} from '../types/api'

export type UploadMode='fo'|'construction'|'single'|'recovery'
export type RecoverySource={batchId:string;item:PendingUpload;file:File}
type Completion={batchId:string}|{sam?:string}
/** Mounted in Shell: hiding the dialog never unmounts the active transfer. */
export const useUploadCenterStore=defineStore('upload-center',()=>{
  const visible=ref(false),mounted=ref(false),busy=ref(false),progress=ref(0),session=ref(0)
  const label=ref(''),mode=ref<UploadMode>('fo'),sam=ref(''),samLabel=ref(''),batchId=ref('')
  const recovery=shallowRef<RecoverySource|null>(null)
  const lastCompleted=shallowRef<Completion|null>(null)
  function launch(next:Exclude<UploadMode,'recovery'>,selectedSam='',selectedLabel=''){
    if(busy.value){
      visible.value=true
      return
    }
    recovery.value=null
    batchId.value=''
    session.value+=1
    mode.value=next;sam.value=selectedSam;samLabel.value=selectedLabel
    progress.value=0;label.value='';mounted.value=true;visible.value=true
  }
  function resume(source:RecoverySource){
    if(busy.value){visible.value=true;return}
    recovery.value=source
    batchId.value=source.batchId
    session.value+=1
    mode.value='recovery'
    report(true,0,'Проверяем оригинал…')
    mounted.value=true;visible.value=true
  }
  function report(running:boolean,percent:number,phase:string){
    busy.value=running
    progress.value=Math.max(0,Math.min(100,Number.isFinite(percent)?percent:0))
    label.value=phase
  }
  function close(){visible.value=false}
  function finish(completion?:Completion){
    busy.value=false;visible.value=false;mounted.value=false;progress.value=0;label.value=''
    recovery.value=null;batchId.value=''
    if(completion)lastCompleted.value=completion
  }
  return {visible,mounted,busy,progress,label,mode,sam,samLabel,batchId,session,recovery,lastCompleted,launch,resume,report,close,finish}
})
