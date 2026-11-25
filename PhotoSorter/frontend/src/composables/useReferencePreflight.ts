import {onUnmounted,ref,shallowRef} from 'vue'
import {referenceImportsApi} from '../api/referenceImports'
import {fileSha256,reviewReferences} from '../utils/referenceDuplicates'
import {errorText} from '../utils/format'
import type {CheckedReference,ReferenceReview,ReferenceTransferItem} from '../types/referenceTransfer'

/** Read-only preflight, independent of the shared transfer queue. */
export function useReferencePreflight(){
  const busy=ref(false),error=ref(''),phase=ref('')
  const review=shallowRef<ReferenceReview|null>(null)
  let controller:AbortController|null=null
  function reset(){review.value=null;error.value='';phase.value=''}
  async function inspect(items:readonly ReferenceTransferItem[]){
    if(busy.value||!items.length)return
    reset()
    busy.value=true
    controller=new AbortController()
    const signal=controller.signal
    try{
      const checked:CheckedReference[]=[]
      for(const [index,item] of items.entries()){
        signal.throwIfAborted()
        phase.value='Проверка файлов на дубли · '+index+' из '+items.length
        const hash=await fileSha256(item.entry.file)
        if(!hash)throw new Error('Не удалось прочитать файл «'+item.entry.file.name+'». Для проверки нужен HTTPS и поддержка SHA-256.')
        checked.push({...item,sha256:hash})
      }
      signal.throwIfAborted()
      phase.value='Сравниваем с библиотекой образцов…'
      const result=await referenceImportsApi.compare(checked.map(({sam,sha256,entry,side})=>
        ({sam,sha256,size:entry.file.size,side:side||null})),signal)
      signal.throwIfAborted()
      if(result.side_conflicts?.length){
        const details=result.side_conflicts.slice(0,10).map(conflict=>
          (checked[conflict.index]?.entry.relative||'Образец')+': '+
          (conflict.existing_side||'Без стороны')+' → '+conflict.requested_side)
        throw new Error('Конфликт сторон ('+result.side_conflicts.length+'). Существующие стороны не изменены. '+details.join('; '))
      }
      review.value=reviewReferences(checked,result.duplicates)
      phase.value=''
    }catch(e){
      phase.value=''
      error.value=signal.aborted?'Проверка остановлена. Её можно запустить снова.':errorText(e)
    }finally{busy.value=false;controller=null}
  }

  function pause(){controller?.abort()}
  onUnmounted(pause)
  return {busy,error,phase,review,reset,inspect,pause}
}
