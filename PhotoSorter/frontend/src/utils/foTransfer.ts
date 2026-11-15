import {batchApi} from '../api/batches'
import {ApiError} from '../api/client'
import {uploadOne,expectedUploadId,newUploadId,resumePendingUpload} from './upload'
import {withUploadRetry} from './uploadRetry'
import {runUploadQueue} from './uploadQueue'
import {errorText} from './format'
import type {BatchUploadManifest,UploadManifestFile} from '../types/api'
import type {UploadContext,UploadResult,UploadSource} from '../types/uploadQueue'

type FolderUpload=Extract<UploadSource,{kind:'fo'}>

export function createFoTransfer(selection:FolderUpload){
  const {entries,name}=selection
  // A deliberate new import gets its own request ID, even if the files and
  // title match. Retrying this transfer must not create a second batch.
  let batchId=selection.resumeBatchId||'',batchName=name,creationRequestId=''
  return async function transfer({signal,parallel,report,setBatch}:UploadContext):Promise<UploadResult>{
    let {autoProcess,threshold}=selection
    let amounts=entries.map(()=>0),completed=new Set<number>()
    let firstError='',phase='Подготовка партии…',sentBytes=0
    const totalBytes=entries.reduce((sum,e)=>sum+e.file.size,0)
    const publish=()=>report({phase,sentBytes,totalBytes,completed:completed.size,totalFiles:entries.length})
    const update=(idx:number,n:number)=>{
      sentBytes+=n-amounts[idx]!
      amounts[idx]=n;publish()
    }
    try{
      publish()
      const request=<T,>(fn:()=>Promise<T>)=>withUploadRetry(fn,signal)
      const matches=(manifest:BatchUploadManifest)=>{
        if(manifest.files.length!==entries.length)return false
        const files=new Map(manifest.files.map(file=>[file.relative_path,file]))
        return entries.every(e=>{
          const match=files.get(e.relative)
          return match?.filename===e.file.name && match.size===e.file.size
        })
      }
      if(!batchId){
        creationRequestId||=newUploadId()
        const created=await request(()=>batchApi.create(name,creationRequestId,signal))
        batchId=created.batch_id;batchName=created.display_name
      }
      setBatch(batchId,batchName)
      phase='Проверка состава папки…';publish()
      let manifestIds:string[]|null=null
      const current=await request(()=>batchApi.manifest(batchId))
      if(selection.resumeBatchId&&current.state==='legacy')
        throw new Error('У этой партии нет манифеста. Продолжите передачу отдельных файлов в её карточке.')
      if(current.state!=='legacy'){
        if(!matches(current))throw new Error('Состав папки не совпадает с манифестом. Выберите исходную папку этого ФО.')
        autoProcess=current.auto_process_state==='waiting'||current.auto_process_state==='queued'
        threshold=current.auto_process_threshold??.50
        const byPath=new Map(current.files.map(file=>[file.relative_path,file]))
        const received=entries.map(entry=>byPath.get(entry.relative)!)
        manifestIds=received.map(file=>file.upload_id)
        completed=new Set(received.flatMap((file,index)=>file.state==='finalized'?[index]:[]))
        amounts=received.map(file=>file.state==='finalized'?file.size:
          file.state==='unfinished'?Math.max(0,Math.min(file.received,file.size)):0)
        sentBytes=amounts.reduce((sum,n)=>sum+n,0)
        publish()
      }else{
        const target={kind:'fo' as const,batchId}
        const plan:UploadManifestFile[]=entries.map(e=>({
          upload_id:expectedUploadId(target,e),relative_path:e.relative,
          filename:e.file.name,size:e.file.size
        }))
        await request(()=>batchApi.registerManifest(batchId,plan,autoProcess,threshold,selection.profile))
        manifestIds=plan.map(e=>e.upload_id)
      }
      const reconnecting=new Set<number>()
      phase='Передача файлов';publish()
      const pending=entries.map((_,index)=>index).filter(index=>current.state==='legacy'||!completed.has(index))
      const failures=await runUploadQueue(pending.length,parallel,signal,async position=>{
        const idx=pending[position]!
        const entry=entries[idx]
        if(!entry)return
        await uploadOne({kind:'fo',batchId:batchId},entry,signal,n=>{
          update(idx,n)
        },state=>{
          if(state.state==='waiting')reconnecting.add(idx)
          else reconnecting.delete(idx)
          phase=reconnecting.size
            ?'Ожидание соединения · '+reconnecting.size+' файлов восстанавливаются'
            :'Передача файлов'
          publish()
        },manifestIds?.[idx])
        reconnecting.delete(idx)
        phase=reconnecting.size?'Ожидание соединения':'Передача файлов'
        completed.add(idx);update(idx,entry.file.size)
      },{
        haltAfterFailuresWithoutSuccess:Math.min(3,parallel),
        onFailure:failure=>{
          if(firstError)return
          const file=entries[pending[failure.index]!]?.file.name||'Неизвестный файл'
          const code=failure.error instanceof ApiError&&failure.error.status
            ?'HTTP '+failure.error.status+' · ':''
          firstError='Ошибка «'+file+'»: '+code+errorText(failure.error)
        }
      })
      if(failures.length){
        const last=manifestIds?await request(()=>batchApi.manifest(batchId)):null
        if(last?.state!=='complete'){
          const details=failures.slice(0,3).map(({index,error})=>
            entries[pending[index]!]?.file.name+': '+errorText(error)).join('; ')
          throw new Error('Не загружено '+failures.length+' из '+entries.length+' файлов: '+details)
        }
      }
      if(manifestIds){
        phase='Проверка полноты партии…';publish()
        const confirmed=await request(()=>batchApi.manifest(batchId))
        if(confirmed.state!=='complete')
          throw new Error('Сервер ожидает ещё '+confirmed.pending+' файлов. Продолжите загрузку из карточки ФО.')
      }
      return {message:autoProcess
        ?'Все файлы партии сохранены. Сортировка запустится после подготовки.'
        :'Все файлы партии сохранены. Превью и нужные форматы готовятся автоматически.',
        completion:{batchId},action:{to:'/fo/'+batchId,label:'Открыть'}}
    }catch(e){
      if(signal.aborted)throw e
      throw new Error(firstError?firstError+' · '+errorText(e):errorText(e))
    }
  }
}

export async function transferRecovery({batchId,item,file}:Extract<UploadSource,{kind:'recovery'}>['source'],
  {signal,report}:UploadContext):Promise<UploadResult>{
  let sentBytes=item.received,phase='Проверяем оригинал…'
  const publish=()=>report({phase,sentBytes,totalBytes:item.size,completed:0,totalFiles:1})
  publish()
  await resumePendingUpload(item.id,{kind:'fo',batchId},{file,relative:file.name},item,signal,
    count=>{sentBytes=count;publish()},
    state=>{
      phase=state.state==='waiting'
        ?'Ожидание соединения · повтор через '+Math.ceil((state.delayMs||1000)/1000)+' с'
        :'Передача файлов'
      publish()
    })
  return {message:'Загрузка фото завершена: '+item.filename,completion:{batchId},
    action:{to:'/fo/'+batchId,label:'Открыть'}}
}
