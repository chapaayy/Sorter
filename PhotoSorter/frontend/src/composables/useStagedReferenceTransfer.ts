import {ref} from 'vue'
import {ApiError} from '../api/client'
import {referenceImportsApi} from '../api/referenceImports'
import {referenceApi} from '../api/references'
import {fileSha256,indexReferenceHashes} from '../utils/referenceDuplicates'
import {runUploadQueue} from '../utils/uploadQueue'
import {withUploadRetry} from '../utils/uploadRetry'
import {errorText} from '../utils/format'
import type {ReferenceTransferItem} from './useReferenceTransfer'
import type {ManifestFile,ReferenceImportStatus} from '../api/referenceImports'

const CHUNK=16*1024*1024
type SavedSession={sessionId:string;ids:string[];manifestKey:string}
function stableKey(items:readonly ReferenceTransferItem[]):string{
  const lines=items.map(i=>[i.sam,i.address||'',i.entry.relative,i.entry.file.name,i.entry.file.size].join('|'))
  const encoded=lines.join('\n')
  let hash=2166136261
  for(let i=0;i<encoded.length;i++)hash=Math.imul(hash^encoded.charCodeAt(i),16777619)
  return 'ps.reference-staging:'+items.length+':'+(hash>>>0).toString(16)
}
function saved(key:string):SavedSession|null{
  try{
    const value=localStorage.getItem(key)
    if(!value)return null
    const obj=JSON.parse(value) as SavedSession
    return obj?.sessionId&&Array.isArray(obj.ids)&&obj.manifestKey===key?obj:null
  }catch{return null}
}
function store(key:string,value:SavedSession){
  try{localStorage.setItem(key,JSON.stringify(value))}catch{/* private mode: current tab still works */}
}
function remove(key:string){
  try{localStorage.removeItem(key)}catch{/* no-op */}
}

/** Manifest-first, server-authoritative resumable staging. Never writes legacy refs. */
export function useStagedReferenceTransfer(){
  const busy=ref(false),error=ref(''),phase=ref(''),completed=ref(0),duplicates=ref(0),sentBytes=ref(0)
  let controller:AbortController|null=null

  async function start(items:readonly ReferenceTransferItem[],parallel:number):Promise<boolean>{
    if(busy.value||!items.length)return false
    busy.value=true;error.value='';completed.value=0;duplicates.value=0;sentBytes.value=0
    controller=new AbortController()
    const signal=controller.signal
    const key=stableKey(items)
    const amounts=items.map(()=>0)
    const update=(i:number,n:number)=>{
      amounts[i]=n
      sentBytes.value=amounts.reduce((sum,value)=>sum+value,0)
    }
    try{
      const request=<T,>(fn:()=>Promise<T>)=>withUploadRetry(fn,signal,s=>
        {phase.value=s.state==='waiting'?'Ожидание соединения · повтор '+s.attempt:'Передача файлов'})
      phase.value='Проверка контрольных сумм…'
      // A full hash binds the selected file to the immutable session manifest,
      // including a fresh browser selection after disconnect/refresh.
      const hashes:string[]=[]
      for(let i=0;i<items.length;i++){
        if(signal.aborted)throw new DOMException('Пауза','AbortError')
        const digest=await fileSha256(items[i]!.entry.file)
        if(!digest)throw new Error('Нужен HTTPS и поддержка SHA-256 в браузере')
        hashes.push(digest)
        phase.value='Проверка файлов '+(i+1)+'/'+items.length
      }
      let session=saved(key)
      if(session&&session.ids.length!==items.length){session=null;remove(key)}
      if(!session){
        session={sessionId:crypto.randomUUID(),ids:items.map(()=>crypto.randomUUID()),manifestKey:key}
        store(key,session)
      }
      const sid=session.sessionId
      const manifest:ManifestFile[]=items.map((item,i)=>({
        upload_id:session!.ids[i]!,
        sam:item.sam,
        address:item.address||null,
        relative_path:item.entry.relative,
        filename:item.entry.file.name,
        size:item.entry.file.size,
        sha256:hashes[i]!
      }))
      phase.value='Регистрация полного списка образцов…'
      await request(()=>referenceImportsApi.create(sid))
      let state:ReferenceImportStatus
      try{state=await request(()=>referenceImportsApi.register(sid,manifest))}
      catch(e){
        if(e instanceof ApiError&&e.status===409){
          remove(key)
          throw new Error('Файлы отличаются от ранее зарегистрированной сессии. Выберите оригинальную папку или начните новый импорт.')
        }
        throw e
      }
      if(state.expected!==items.length||state.files.length!==items.length)
        throw new Error('Сервер вернул неполный манифест образцов')
      const knownFiles=await referenceApi.files().catch(()=>({files:[]}))
      const known=indexReferenceHashes(knownFiles.files)
      const byId=new Map(state.files.map(file=>[file.upload_id,file]))
      phase.value='Передача файлов'
      const failures=await runUploadQueue(items.length,parallel,signal,async i=>{
        const item=items[i]!,entry=manifest[i]!
        const existing=byId.get(entry.upload_id)
        if(!existing||existing.sha256!==hashes[i]||existing.size!==entry.size||
           existing.relative_path!==entry.relative_path||existing.sam!==entry.sam)
          throw new Error('Состав файлов на сервере не соответствует выбранной папке')
        if(existing.state==='finalized'||existing.state==='duplicate'){
          update(i,item.entry.file.size);completed.value++
          if(existing.state==='duplicate')duplicates.value++
          return
        }
        const knownHashes=known.get(item.sam)
        if(knownHashes?.has(hashes[i]!)){
          try{
            await request(()=>referenceImportsApi.duplicate(sid,entry.upload_id,hashes[i]!))
            update(i,item.entry.file.size);completed.value++;duplicates.value++
            return
          }catch(e){
            // The server may have removed the old source; send the bytes.
            if(!(e instanceof ApiError)||e.status!==409)throw e
          }
        }
        let stateFile=await request(()=>referenceImportsApi.file(sid,entry.upload_id))
        let offset=stateFile.offset
        if(stateFile.state!=='pending'){
          update(i,item.entry.file.size);completed.value++
          if(stateFile.state==='duplicate')duplicates.value++
          return
        }
        update(i,offset)
        while(offset<item.entry.file.size){
          if(signal.aborted)throw new DOMException('Пауза','AbortError')
          const data=new Uint8Array(await item.entry.file.slice(offset,offset+CHUNK).arrayBuffer())
          try{
            const response=await request(()=>referenceImportsApi.append(sid,entry.upload_id,offset,data,signal))
            if(response.offset<=offset||response.offset>item.entry.file.size)
              throw new Error('Неверное смещение образца от сервера')
            offset=response.offset
            update(i,offset)
          }catch(e){
            if(!(e instanceof ApiError)||e.status!==409)throw e
            stateFile=await request(()=>referenceImportsApi.file(sid,entry.upload_id))
            if(stateFile.state!=='pending'){
              offset=item.entry.file.size;update(i,offset);break
            }
            if(stateFile.offset===offset)throw e
            offset=stateFile.offset;update(i,offset)
          }
        }
        const result=await request(()=>referenceImportsApi.finish(sid,entry.upload_id))
        if(result.sha256!==hashes[i])throw new Error('Контрольная сумма образца изменилась')
        if(result.already_present)duplicates.value++
        completed.value++;update(i,item.entry.file.size)
      },{
        haltAfterFailuresWithoutSuccess:Math.min(3,Math.max(1,parallel)),
        onFailure:f=>{if(!error.value)error.value=items[f.index]?.entry.file.name+': '+errorText(f.error)}
      })
      if(failures.length)
        throw new Error('Не завершено '+failures.length+' файлов: '+
          failures.slice(0,4).map(f=>items[f.index]?.entry.file.name+': '+errorText(f.error)).join('; '))
      phase.value='Проверка готовности сессии…'
      state=await request(()=>referenceImportsApi.status(sid))
      if(state.state!=='complete'||state.pending!==0)
        throw new Error('Сервер ожидает ещё '+state.pending+' файлов, выберите исходные файлы повторно')
      await request(()=>referenceImportsApi.complete(sid))
      remove(key)
      phase.value='Подготовка образцов поставлена в очередь'
      return true
    }catch(e){
      error.value=signal.aborted?'Передача приостановлена. Повторно выберите те же файлы для продолжения.':
        error.value?error.value+' · '+errorText(e):errorText(e)
      return false
    }finally{busy.value=false;controller=null}
  }
  function pause(){controller?.abort()}
  return {busy,error,phase,completed,duplicates,sentBytes,start,pause}
}
