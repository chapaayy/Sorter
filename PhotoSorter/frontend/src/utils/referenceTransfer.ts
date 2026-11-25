import {ApiError} from '../api/client'
import {referenceImportsApi} from '../api/referenceImports'
import {runUploadQueue} from '../utils/uploadQueue'
import {withUploadRetry} from '../utils/uploadRetry'
import {errorText} from '../utils/format'
import type {ReferenceReview,ReferenceTransferItem} from '../types/referenceTransfer'
import type {ManifestFile,ReferenceImportStatus} from '../api/referenceImports'

import type {UploadContext,UploadResult} from '../types/uploadQueue'

export const ALL_DUPLICATES='Все выбранные фото уже есть в библиотеке. В очередь ничего не добавлено.'
const CHUNK=16*1024*1024
type SavedSession={sessionId:string;ids:string[];manifestKey:string}
function stableKey(items:readonly ReferenceTransferItem[]):string{
  const withSides=items.some(i=>!!i.side)
  const lines=items.map(i=>[i.sam,i.address||'',i.entry.relative,i.entry.file.name,i.entry.file.size,
    ...(withSides?[i.side||'']:[])].join('|'))
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

export async function transferReferences(confirmed:ReferenceReview,success:string,
  {signal,parallel,report}:UploadContext):Promise<UploadResult>{
    const items=confirmed.newFiles
    let completed=0,duplicates=0,sentBytes=0,totalBytes=confirmed.totalBytes
    let phase='Регистрация списка образцов…',firstError=''
    const publish=()=>report({sentBytes,totalBytes,completed,totalFiles:items.length,duplicates,phase})
    const key=stableKey(items)
    const amounts=items.map(()=>0)
    const update=(i:number,n:number)=>{
      sentBytes+=n-amounts[i]!
      amounts[i]=n
      publish()
    }
    const skip=(i:number)=>{
      // Bytes already transmitted during this attempt still count, even if
      // another import published the photo after the comparison.
      totalBytes-=items[i]!.entry.file.size-amounts[i]!
      completed++;duplicates++
      publish()
    }
    try{
      publish()
      const request=<T,>(fn:()=>Promise<T>)=>withUploadRetry(fn,signal,s=>
        {phase=s.state==='waiting'?'Ожидание соединения · повтор '+s.attempt:'Передача файлов';publish()})
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
        sha256:item.sha256,
        ...(item.side?{side:item.side}:{})
      }))
      phase='Регистрация полного списка образцов…';publish()
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
      phase='Передача файлов';publish()
      const failures=await runUploadQueue(items.length,parallel,signal,async i=>{
        const item=items[i]!,entry=manifest[i]!
        const existing=byId.get(entry.upload_id)
        if(!existing||existing.sha256!==item.sha256||existing.size!==entry.size||
           existing.relative_path!==entry.relative_path||existing.sam!==entry.sam||
           (existing.side||null)!==(entry.side||null))
          throw new Error('Состав файлов на сервере не соответствует выбранной папке')
        if(existing.state==='duplicate'){skip(i);return}
        if(existing.state==='finalized'){
          completed++;update(i,item.entry.file.size)
          return
        }
        let stateFile=await request(()=>referenceImportsApi.file(sid,entry.upload_id))
        let offset=stateFile.offset
        if(stateFile.state==='duplicate'){skip(i);return}
        if(stateFile.state!=='pending'){
          completed++;update(i,item.entry.file.size)
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
        if(result.already_present)duplicates++
        completed++;update(i,item.entry.file.size)
      },{
        haltAfterFailuresWithoutSuccess:Math.min(3,Math.max(1,parallel)),
        onFailure:f=>{if(!firstError)firstError=items[f.index]?.entry.file.name+': '+errorText(f.error)}
      })
      if(failures.length)
        throw new Error('Не завершено '+failures.length+' файлов: '+
          failures.slice(0,4).map(f=>items[f.index]?.entry.file.name+': '+errorText(f.error)).join('; '))
      phase='Проверка готовности сессии…';publish()
      state=await request(()=>referenceImportsApi.status(sid))
      if(state.state!=='complete'||state.pending!==0)
        throw new Error('Сервер ожидает ещё '+state.pending+' файлов, выберите исходные файлы повторно')
      const result=await request(()=>referenceImportsApi.complete(sid))
      remove(key)
      return result.state==='queued'
        ?{message:success,completion:{},action:{to:'/queue',label:'К очереди'}}
        :{message:ALL_DUPLICATES}
    }catch(e){
      if(signal.aborted)throw e
      throw new Error(firstError?firstError+' · '+errorText(e):errorText(e))
    }
}
