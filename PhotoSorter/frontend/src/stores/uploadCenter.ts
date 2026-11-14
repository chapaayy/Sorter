import {defineStore} from 'pinia'
import {reactive,shallowRef} from 'vue'
import type {PendingUpload} from '../types/api'

export type UploadMode='fo'|'construction'|'library'|'single'|'recovery'
export type UploadChannel='fo'|'references'
export type RecoverySource={batchId:string;item:PendingUpload;file:File}
type Completion={batchId:string}|{sam?:string}
const newWindow=(mode:UploadMode)=>({
  visible:false,mounted:false,busy:false,progress:0,session:0,label:'',mode,sam:'',samLabel:'',batchId:'',
  recovery:null as RecoverySource|null
})

/** Each transfer keeps its files mounted in Shell when its window is hidden. */
export const useUploadCenterStore=defineStore('upload-center',()=>{
  const windows=reactive({fo:newWindow('fo'),references:newWindow('library')})
  const lastCompleted=shallowRef<Completion|null>(null)
  function show(channel:UploadChannel){
    windows[channel==='fo'?'references':'fo'].visible=false
    windows[channel].visible=true
  }
  function launch(mode:Exclude<UploadMode,'recovery'>,sam='',samLabel=''){
    const channel=mode==='fo'?'fo':'references'
    const job=windows[channel]
    if(!job.busy)Object.assign(job,newWindow(mode),{sam,samLabel,session:job.session+1,mounted:true})
    show(channel)
  }
  function resume(source:RecoverySource){
    const job=windows.fo
    if(!job.busy)Object.assign(job,newWindow('recovery'),{
      recovery:source,batchId:source.batchId,session:job.session+1,
      busy:true,label:'Проверяем оригинал…',mounted:true
    })
    show('fo')
  }
  function report(channel:UploadChannel,running:boolean,percent:number,phase:string){
    const job=windows[channel]
    job.busy=running
    job.progress=Math.max(0,Math.min(100,Number.isFinite(percent)?percent:0))
    job.label=phase
  }
  function close(channel:UploadChannel){windows[channel].visible=false}
  function finish(channel:UploadChannel,completion?:Completion){
    const job=windows[channel]
    Object.assign(job,newWindow(job.mode),{session:job.session})
    if(completion)lastCompleted.value=completion
  }
  return {windows,lastCompleted,launch,resume,report,show,close,finish}
})
