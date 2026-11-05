import {api,post,ApiError} from '../api/client'
export interface UploadTarget{kind:'fo'|'reference';batchId?:string;sam?:string}
export interface UploadResult{path:string;sha256?:string;already_finalized?:boolean}
export interface UploadEntry{file:File;relative:string}
export const ALLOWED=/\.(jpe?g|png|webp|bmp|tiff?)$/i
const MAX_FILE=60*1024*1024
export const UPLOAD_CHUNK_BYTES=16*1024*1024
function key(t:UploadTarget,entry:UploadEntry){
  return 'ps.up.v3.'+[t.kind,t.batchId||t.sam||'',entry.relative,entry.file.size,entry.file.lastModified].join(':')
}
function saved(k:string){try{return localStorage.getItem(k)}catch{return null}}
function remember(k:string,value:string|null){try{if(value)localStorage.setItem(k,value);else localStorage.removeItem(k)}catch{}}
async function resume(id:string,t:UploadTarget,e:UploadEntry,signal:AbortSignal,progress:(n:number)=>void):Promise<UploadResult>{
  let status:{offset:number;size:number;finalized:boolean}
  if(id){
    try{status=await api('/uploads/'+id)}
    catch(error){
      if(!(error instanceof ApiError)||error.status!==404)throw error
      const created=await post<{id:string}>('/uploads',{kind:t.kind,batch_id:t.batchId||null,sam:t.sam||null,filename:e.file.name,size:e.file.size})
      id=created.id
      remember(key(t,e),id)
      status={offset:0,size:e.file.size,finalized:false}
    }
  }else{
    const created=await post<{id:string}>('/uploads',{kind:t.kind,batch_id:t.batchId||null,sam:t.sam||null,filename:e.file.name,size:e.file.size})
    id=created.id
    remember(key(t,e),id)
    status={offset:0,size:e.file.size,finalized:false}
  }
  if(status.size!==e.file.size)throw new Error('Файл отличается по размеру от сохранённой загрузки')
  if(status.finalized){progress(e.file.size);return {path:'',already_finalized:true}}
  let offset=status.offset,retries=0
  while(offset<e.file.size){
    if(signal.aborted)throw new DOMException('Остановлено','AbortError')
    const chunk=e.file.slice(offset,Math.min(offset+UPLOAD_CHUNK_BYTES,e.file.size))
    try{
      const next=await api<{offset:number}>('/uploads/'+id,{method:'PATCH',body:chunk,headers:{'upload-offset':String(offset),'Content-Type':'application/octet-stream'},signal})
      if(!Number.isSafeInteger(next.offset)||next.offset<=offset||next.offset>e.file.size)
        throw new Error('Некорректный offset от сервера')
      offset=next.offset;retries=0;progress(offset)
    }catch(err){
      if(signal.aborted)throw err
      if(err instanceof ApiError&&err.status===409){
        status=await api('/uploads/'+id)
        if(status.finalized){progress(e.file.size);return {path:'',already_finalized:true}}
        if(status.offset===offset)throw err
        offset=status.offset;progress(offset);continue
      }
      if(err instanceof ApiError&&[413,422,507,403].includes(err.status))throw err
      if(++retries>=4)throw err
      await new Promise(resolve=>setTimeout(resolve,retries*650))
      status=await api('/uploads/'+id);offset=status.offset
    }
  }
  return api<UploadResult>('/uploads/'+id+'/finish',{method:'POST',signal})
}
export async function uploadOne(t:UploadTarget,e:UploadEntry,signal:AbortSignal,progress:(n:number)=>void):Promise<UploadResult>{
  if(!ALLOWED.test(e.file.name))throw new Error('Неподдерживаемое изображение: '+e.file.name)
  if(e.file.size>MAX_FILE)throw new Error('Файл превышает лимит 60 МБ: '+e.file.name)
  if(e.file.size===0)throw new Error('Пустой файл: '+e.file.name)
  const storage=key(t,e)
  const previous=saved(storage)
  if(previous==='done'){progress(e.file.size);return {path:'',already_finalized:true}}
  // Restore the original 16 MiB offset-based protocol (5 workers by default).
  // Existing direct-transfer upload IDs are also resumed safely via GET.
  const result=await resume(previous||'',t,e,signal,progress)
  remember(storage,'done')
  progress(e.file.size)
  return result
}
export function directoryEntries(files:FileList):{folder:string;entries:UploadEntry[]}{
  const entries=Array.from(files).filter(f=>ALLOWED.test(f.name)).map(f=>({file:f,relative:f.webkitRelativePath||f.name}))
  if(!entries.length)throw new Error('В папке не найдено поддерживаемых изображений')
  const roots=new Set(entries.map(e=>e.relative.split('/')[0]))
  if(roots.size!==1||!entries[0]?.relative.includes('/'))throw new Error('Выберите одну целую папку ФО')
  return {folder:entries[0].relative.split('/')[0]||'Фотоотчёт',entries}
}
