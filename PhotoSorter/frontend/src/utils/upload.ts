import {api,ApiError} from '../api/client'
import {withUploadRetry} from './uploadRetry'
import type {TransferState} from './uploadRetry'

export interface UploadTarget{kind:'fo'|'reference';batchId?:string;sam?:string;address?:string}
export interface UploadResult{path:string;sha256?:string;already_finalized?:boolean;already_present?:boolean}
export interface UploadEntry{file:File;relative:string}
export interface PendingFileIdentity{filename:string;size:number;has_part:boolean;prefix_bytes:number;prefix_sha256:string|null}
export const ALLOWED=/\.(jpe?g|png|webp|bmp|tiff?)$/i
export const MAX_IMAGE_UPLOAD_BYTES=60*1024*1024
export const MAX_FO_UPLOAD_BYTES=2*1024**3
export const UPLOAD_CHUNK_BYTES=16*1024*1024
// Browser MIME is a selection hint, not an authoritative upload check.
const OTHER_MEDIA=/\.(avif|heic|heif|hif|jxl|gif|svgz?|ico|jp2|j2k|jpf|jpx|jpm|j2c|jpc|psd|psb|dng|cr2|cr3|crw|nef|nrw|arw|raf|orf|rw2|pef|sr2|srw|x3f|raw|tga|exr|hdr|dds|icns|ppm|pgm|pbm|pnm|mp4|m4v|mov|qt|avi|mkv|webm|mpg|mpeg|mpe|m2v|mts|m2ts|ts|3gp|3g2|wmv|asf|flv|f4v|ogv|vob|mxf|rmvb|dv)$/i
const OS_METADATA=new Set(['thumbs.db','ehthumbs.db','desktop.ini','.ds_store'])
function foMediaCandidate(file:File):boolean{
  return /^(image|video)\//i.test(file.type)||ALLOWED.test(file.name)||OTHER_MEDIA.test(file.name)
}

function key(t:UploadTarget,entry:UploadEntry){
  return 'ps.up.v3.'+[t.kind,t.batchId||t.sam||'',entry.relative,entry.file.size,entry.file.lastModified].join(':')
}
function saved(k:string){try{return localStorage.getItem(k)}catch{return null}}
function remember(k:string,value:string|null){try{if(value)localStorage.setItem(k,value);else localStorage.removeItem(k)}catch{}}
function newUploadId():string{
  if(typeof crypto==='undefined')throw new Error('Для защищённой передачи нужен HTTPS')
  if(typeof crypto.randomUUID==='function')return crypto.randomUUID()
  const data=crypto.getRandomValues(new Uint8Array(16))
  data[6]=(data[6]&15)|64;data[8]=(data[8]&63)|128
  const hex=Array.from(data,x=>x.toString(16).padStart(2,'0')).join('')
  return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-')
}
type Status={offset:number;size:number;finalized:boolean}

async function resume(id:string,t:UploadTarget,e:UploadEntry,signal:AbortSignal,
  progress:(n:number)=>void,onState?:(state:TransferState)=>void,
  allowCreate=true):Promise<UploadResult>{
  const request=<T>(fn:()=>Promise<T>)=>withUploadRetry(fn,signal,onState)
  const store=key(t,e)
  let status:Status
  if(id){
    try{status=await request(()=>api<Status>('/uploads/'+id,{signal}))}
    catch(error){
      if(!(error instanceof ApiError)||error.status!==404||!allowCreate)throw error
      status=await createSession(id)
    }
  }else{
    if(!allowCreate)throw new Error('Отсутствует ID незавершённой передачи')
    id=newUploadId()
    remember(store,id) // Persist BEFORE network request: the POST reply may be lost.
    status=await createSession(id)
  }

  async function createSession(clientId:string):Promise<Status>{
    const created=await request(()=>api<{id:string;size:number;offset:number;finalized:boolean}>(
      '/uploads',{method:'POST',body:JSON.stringify({
        kind:t.kind,batch_id:t.batchId||null,sam:t.sam||null,address:t.address||null,
        filename:e.file.name,size:e.file.size,client_upload_id:clientId
      }),signal}))
    if(created.id!==clientId)throw new Error('Сервер вернул другой идентификатор загрузки')
    return created
  }

  if(status.size!==e.file.size)throw new Error('Файл отличается по размеру от сохранённой загрузки')
  if(!Number.isSafeInteger(status.offset)||status.offset<0||status.offset>e.file.size)
    throw new Error('Некорректное смещение файла на сервере')
  if(status.finalized){progress(e.file.size);return {path:'',already_finalized:true,already_present:true}}
  let offset=status.offset
  progress(offset)
  while(offset<e.file.size){
    if(signal.aborted)throw new DOMException('Загрузка остановлена','AbortError')
    const chunk=e.file.slice(offset,Math.min(offset+UPLOAD_CHUNK_BYTES,e.file.size))
    try{
      const next=await request(()=>api<{offset:number}>('/uploads/'+id,{
        method:'PATCH',body:chunk,headers:{
          'upload-offset':String(offset),'Content-Type':'application/octet-stream'
        },signal}))
      if(!Number.isSafeInteger(next.offset)||next.offset<=offset||next.offset>e.file.size)
        throw new Error('Некорректный offset от сервера')
      offset=next.offset;progress(offset)
    }catch(error){
      if(signal.aborted)throw error
      if(error instanceof ApiError&&error.status===409){
        status=await request(()=>api<Status>('/uploads/'+id,{signal}))
        if(status.finalized){progress(e.file.size);return {path:'',already_finalized:true,already_present:true}}
        if(status.offset===offset)throw error
        if(!Number.isSafeInteger(status.offset)||status.offset<0||status.offset>e.file.size)
          throw new Error('Некорректный offset от сервера')
        offset=status.offset;progress(offset);continue
      }
      throw error
    }
  }
  // If the VPN dies after all bytes arrive, retry ONLY this finish call.
  return request(()=>api<UploadResult>('/uploads/'+id+'/finish',{method:'POST',signal}))
}

export function expectedUploadId(t:UploadTarget,e:UploadEntry):string{
  const storage=key(t,e)
  const current=saved(storage)
  if(current&&/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(current))return current
  const id=newUploadId()
  remember(storage,id)
  return id
}

export async function uploadOne(t:UploadTarget,e:UploadEntry,signal:AbortSignal,
  progress:(n:number)=>void,onState?:(state:TransferState)=>void,
  registeredId?:string):Promise<UploadResult>{
  if(t.kind==='reference'&&!ALLOWED.test(e.file.name))throw new Error('Неподдерживаемое изображение: '+e.file.name)
  if(e.file.size>(t.kind==='fo'?MAX_FO_UPLOAD_BYTES:MAX_IMAGE_UPLOAD_BYTES))
    throw new Error('Слишком большой файл: '+e.file.name)
  if(e.file.size===0)throw new Error('Пустой файл: '+e.file.name)
  const storage=key(t,e)
  const previous=saved(storage)
  if(registeredId){
    remember(storage,registeredId)
    const result=await resume(registeredId,t,e,signal,progress,onState)
    // Keep the UUID, not the old 'done' sentinel: after a refresh the
    // server is authoritative about whether this exact file was finalized.
    progress(e.file.size)
    return result
  }
  if(previous==='done'&&t.kind==='fo'){
    progress(e.file.size)
    return {path:'',already_finalized:true,already_present:true}
  }
  const result=await resume(previous==='done'?'':previous||'',t,e,signal,progress,onState)
  remember(storage,'done')
  progress(e.file.size)
  return result
}

/** After refresh browser file permissions are lost. User explicitly selects
 * the source again; a server prefix SHA-256 verifies it is the SAME file.
 */
export async function resumePendingUpload(uploadId:string,t:UploadTarget,e:UploadEntry,
  identity:PendingFileIdentity,signal:AbortSignal,progress:(n:number)=>void,
  onState?:(state:TransferState)=>void):Promise<UploadResult>{
  if(!identity.has_part)throw new Error('Временный файл на сервере отсутствует')
  if(e.file.name!==identity.filename||e.file.size!==identity.size)
    throw new Error('Выберите исходный файл с тем же именем и размером')
  if(identity.prefix_bytes>0){
    if(!identity.prefix_sha256||typeof crypto==='undefined'||!crypto.subtle)
      throw new Error('Не удалось проверить совпадение файла; нужен HTTPS')
    const chunk=await e.file.slice(0,identity.prefix_bytes).arrayBuffer()
    const digest=await crypto.subtle.digest('SHA-256',chunk)
    const hash=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('')
    if(hash!==identity.prefix_sha256.toLowerCase())
      throw new Error('Файл отличается от уже переданной части; выберите правильный оригинал')
  }
  return resume(uploadId,t,e,signal,progress,onState,false)
}
export function directoryEntries(files:ArrayLike<File>,includeUnknown=false):{folder:string;entries:UploadEntry[];unknown:number}{
  const candidates=Array.from(files).filter(f=>!OS_METADATA.has(f.name.toLowerCase())&&!f.name.startsWith('._'))
  const unknown=candidates.filter(f=>!foMediaCandidate(f)).length
  const entries=candidates.filter(f=>includeUnknown||foMediaCandidate(f)).map(f=>({file:f,relative:f.webkitRelativePath||f.name}))
  if(!candidates.length)throw new Error('В папке не найдено фото или видео')
  const path=candidates[0]!.webkitRelativePath
  if(!path.includes('/'))throw new Error('Выберите одну целую папку ФО')
  const roots=new Set(entries.map(e=>e.relative.split('/')[0]))
  if(roots.size>1||entries.some(e=>!e.relative.includes('/')))throw new Error('Выберите одну целую папку ФО')
  for(const {file,relative} of entries){
    if(!file.size)throw new Error('Пустой файл: '+relative)
    if(file.size>MAX_FO_UPLOAD_BYTES)throw new Error('Файл больше 2 ГиБ: '+relative)
    if([...file.name].length>200)throw new Error('Имя файла длиннее 200 символов: '+relative)
  }
  return {folder:path.split('/')[0]||'Фотоотчёт',entries,unknown}
}
