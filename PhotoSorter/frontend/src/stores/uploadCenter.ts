import {defineStore} from 'pinia'
import {ref} from 'vue'

export type UploadMode='fo'|'library'|'single'
/** Mounted in Shell: hiding the dialog never unmounts the active transfer. */
export const useUploadCenterStore=defineStore('upload-center',()=>{
  const visible=ref(false),mounted=ref(false),busy=ref(false),progress=ref(0),session=ref(0)
  const label=ref(''),mode=ref<UploadMode>('fo'),sam=ref(''),samLabel=ref('')
  function launch(next:UploadMode,selectedSam='',selectedLabel=''){
    if(busy.value){
      visible.value=true
      return
    }
    session.value+=1
    mode.value=next;sam.value=selectedSam;samLabel.value=selectedLabel
    progress.value=0;label.value='';mounted.value=true;visible.value=true
  }
  function report(running:boolean,percent:number,phase:string){
    busy.value=running
    progress.value=Math.max(0,Math.min(100,Number.isFinite(percent)?percent:0))
    label.value=phase
  }
  function close(){visible.value=false}
  function finish(){busy.value=false;visible.value=false;mounted.value=false;progress.value=0}
  return {visible,mounted,busy,progress,label,mode,sam,samLabel,session,launch,report,close,finish}
})
