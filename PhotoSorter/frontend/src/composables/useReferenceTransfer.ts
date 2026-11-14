import {computed,onUnmounted,ref,shallowRef} from 'vue'
import {ApiError} from '../api/client'
import {referenceImportsApi} from '../api/referenceImports'
import {fileSha256,reviewReferences} from '../utils/referenceDuplicates'
import {runUploadQueue} from '../utils/uploadQueue'
import {withUploadRetry} from '../utils/uploadRetry'
import {errorText} from '../utils/format'
import type {CheckedReference,ReferenceReview,ReferenceTransferItem} from '../types/referenceTransfer'
import type {Completion,ManifestFile,ReferenceImportStatus} from '../api/referenceImports'

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

/** Manifest-first, server-authoritative resumable staging. Writes only to isolated staged reference storage. */
export function useReferenceTransfer(){
  const busy=ref(false),error=ref(''),phase=ref(''),completed=ref(0),duplicates=ref(0),sentBytes=ref(0)
  const review=shallowRef<ReferenceReview|null>(null),approved=shallowRef<ReferenceReview|null>(null)
  const totalBytes=ref(0),totalFiles=computed(()=>approved.value?.newFiles.length||0)
  const percent=computed(()=>totalBytes.value?100*sentBytes.value/totalBytes.value:0)
  let controller:AbortController|null=null

  function reset(){
    review.value=null;approved.value=null;completed.value=0;duplicates.value=0
    totalBytes.value=0;sentBytes.value=0;error.value='';phase.value=''
  }
  function begin(){
    busy.value=true;error.value=''
    controller=new AbortController()
    return controller.signal
  }
  function end(){busy.value=false;controller=null}

  async function inspect(items:readonly ReferenceTransferItem[]){
    if(busy.value||!items.length)return
    reset()
    const signal=begin()
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
      const result=await referenceImportsApi.compare(checked.map(({sam,sha256,entry})=>
        ({sam,sha256,size:entry.file.size})),signal)
      signal.throwIfAborted()
      review.value=reviewReferences(checked,result.duplicates)
      phase.value=''
    }catch(e){
      phase.value=''
      error.value=signal.aborted?'Проверка остановлена. Её можно запустить снова.':errorText(e)
    }finally{end()}
  }

  async function start(parallel:number):Promise<Completion|null>{
    if(busy.value)return null
    const confirmed=review.value??approved.value
    if(!confirmed?.newFiles.length)return null
    const items=confirmed.newFiles
    approved.value=confirmed;review.value=null
    const signal=begin()
    completed.value=0;duplicates.value=0;sentBytes.value=0;totalBytes.value=confirmed.totalBytes
    const key=stableKey(items)
    const amounts=items.map(()=>0)
    const update=(i:number,n:number)=>{
      sentBytes.value+=n-amounts[i]!
      amounts[i]=n
    }
    const skip=(i:number)=>{
      // Bytes already transmitted during this attempt still count, even if
      // another import published the photo after the comparison.
      totalBytes.value-=items[i]!.entry.file.size-amounts[i]!
      completed.value++;duplicates.value++
    }
    try{
      const request=<T,>(fn:()=>Promise<T>)=>withUploadRetry(fn,signal,s=>
        {phase.value=s.state==='waiting'?'Ожидание соединения · повтор '+s.attempt:'Передача файлов'})
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
        sha256:item.sha256
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
      const byId=new Map(state.files.map(file=>[file.upload_id,file]))
      phase.value='Передача файлов'
      const failures=await runUploadQueue(items.length,parallel,signal,async i=>{
        const item=items[i]!,entry=manifest[i]!
        const existing=byId.get(entry.upload_id)
        if(!existing||existing.sha256!==item.sha256||existing.size!==entry.size||
           existing.relative_path!==entry.relative_path||existing.sam!==entry.sam)
          throw new Error('Состав файлов на сервере не соответствует выбранной папке')
        if(existing.state==='duplicate'){skip(i);return}
        if(existing.state==='finalized'){
          update(i,item.entry.file.size);completed.value++
          return
        }
        let stateFile=await request(()=>referenceImportsApi.file(sid,entry.upload_id))
        let offset=stateFile.offset
        if(stateFile.state==='duplicate'){skip(i);return}
        if(stateFile.state!=='pending'){
          update(i,item.entry.file.size);completed.value++
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
            if(stateFile.state==='duplicate'){skip(i);return}
            if(stateFile.state!=='pending'){
              offset=item.entry.file.size;update(i,offset);break
            }
            if(stateFile.offset===offset)throw e
            offset=stateFile.offset;update(i,offset)
          }
        }
        const result=await request(()=>referenceImportsApi.finish(sid,entry.upload_id))
        if(result.sha256!==item.sha256)throw new Error('Контрольная сумма образца изменилась')
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
      const result=await request(()=>referenceImportsApi.complete(sid))
      remove(key)
      phase.value=result.state==='queued'?'Подготовка образцов поставлена в очередь':'Все файлы уже есть в библиотеке'
      return result
    }catch(e){
      error.value=signal.aborted?'Передача приостановлена. Нажмите «Продолжить загрузку».':
        error.value?error.value+' · '+errorText(e):errorText(e)
      return null
    }finally{end()}
  }
  function pause(){controller?.abort()}
  onUnmounted(pause)
  return {busy,error,phase,completed,duplicates,sentBytes,totalBytes,totalFiles,percent,review,approved,reset,inspect,start,pause}
}
