import {ref} from 'vue'
import {useStagedReferenceTransfer} from './useStagedReferenceTransfer'
import {uploadOne} from '../utils/upload'
import {runUploadQueue} from '../utils/uploadQueue'
import {errorText} from '../utils/format'
import {referenceApi} from '../api/references'
import {fileSha256,indexReferenceHashes} from '../utils/referenceDuplicates'
import type {UploadEntry} from '../utils/upload'

export interface ReferenceTransferItem{sam:string;address?:string;entry:UploadEntry}

/** One upload engine shared by bulk imports and single-construction additions. */
export function useReferenceTransfer(staged=false){
  if(staged)return useStagedReferenceTransfer()
  const phase=ref('')
  const busy=ref(false),error=ref(''),completed=ref(0),duplicates=ref(0),sentBytes=ref(0)
  let controller:AbortController|null=null

  async function start(items:readonly ReferenceTransferItem[],parallel:number):Promise<boolean>{
    if(busy.value||!items.length)return false
    busy.value=true;error.value='';completed.value=0;duplicates.value=0;sentBytes.value=0
    controller=new AbortController()
    const signal=controller.signal
    const amounts=items.map(()=>0)
    try{
      // Do not retransmit unchanged references already present on the server.
      // Failure of this optional lookup falls back to backend-side SHA-256 dedup.
      const known=await referenceApi.files()
        .then(result=>indexReferenceHashes(result.files)).catch(()=>new Map<string,Set<string>>())
      const failures=await runUploadQueue(items.length,parallel,signal,async i=>{
        const item=items[i]
        if(!item)return
        const fingerprints=known.get(item.sam)
        if(fingerprints?.size){
          const digest=await fileSha256(item.entry.file)
          if(signal.aborted)throw new DOMException('Остановлено','AbortError')
          if(digest&&fingerprints.has(digest)){
            amounts[i]=item.entry.file.size
            sentBytes.value=amounts.reduce((sum,current)=>sum+current,0)
            completed.value++;duplicates.value++
            return
          }
        }
        const result=await uploadOne({kind:'reference',sam:item.sam,address:item.address},
          item.entry,signal,n=>{
            amounts[i]=n
            sentBytes.value=amounts.reduce((sum,current)=>sum+current,0)
          })
        completed.value++
        if(result.sha256){
          let hashes=known.get(item.sam)
          if(!hashes){hashes=new Set();known.set(item.sam,hashes)}
          hashes.add(result.sha256.toLowerCase())
        }
        if(result.already_present||result.already_finalized)duplicates.value++
      },{
        haltAfterFailuresWithoutSuccess:Math.min(3,Math.max(1,parallel)),
        onFailure:failure=>{
          if(!error.value)error.value='Ошибка «'+items[failure.index]?.entry.file.name+'»: '+errorText(failure.error)
        }
      })
      if(failures.length){
        error.value='Не загружено '+failures.length+' из '+items.length+' файлов. '+
          failures.slice(0,5).map(({index,error})=>
            items[index]?.entry.relative+': '+errorText(error)).join('; ')
        return false
      }
      return true
    }catch(err){
      error.value=signal.aborted?'Передача приостановлена. Выберите ту же папку или файлы для продолжения.':
        error.value?error.value+' · '+errorText(err):errorText(err)
      return false
    }finally{busy.value=false;controller=null}
  }
  function pause(){controller?.abort()}
  return {busy,error,phase,completed,duplicates,sentBytes,start,pause}
}
