/** Strict, fully-audited selection for bulk construction reference imports.
 * The server remains authoritative for city codes and existing addresses.
 */
import {ALLOWED,MAX_IMAGE_UPLOAD_BYTES} from './upload'
import type {UploadEntry} from './upload'

export interface ConstructionFolder{
  folder:string
  sam:string
  cityCode:string
  number:string
  address:string
  count:number
}
export interface ReferenceUploadTask{
  sam:string
  address:string
  entry:UploadEntry
}
export interface ReferenceSelectionError{path:string;reason:string}
export interface ReferenceSelection{
  tasks:ReferenceUploadTask[]
  folders:ConstructionFolder[]
  errors:ReferenceSelectionError[]
  scanned:number
  totalBytes:number
}

const NAME=/^([A-Z]{2,5}) ([0-9]{1,8}) — (.+)$/
const INVALID_ADDRESS=/[<>:"/\\|?*\x00-\x1f]/

export function parseConstructionFolder(name:string):ConstructionFolder|null{
  const match=NAME.exec(name)
  if(!match)return null
  const [,cityCode,number,address]=match
  if(!cityCode||!number||!address||name.length>200||address.length>120||
     address!==address.trim()||address.endsWith('.')||address.includes('  ')||
     INVALID_ADDRESS.test(address))return null
  return {folder:name,sam:cityCode+' '+number,cityCode,number,address,count:0}
}

export function inspectReferenceDirectory(files:Iterable<File>):ReferenceSelection{
  const tasks:ReferenceUploadTask[]=[],errors:ReferenceSelectionError[]=[]
  const folders=new Map<string,ConstructionFolder>()
  let scanned=0,totalBytes=0
  for(const file of files){
    scanned++
    const relative=file.webkitRelativePath||file.name
    const parts=relative.replace(/\\/g,'/').split('/')
    // The root may be either a named library or a single construction folder.
    // No silently ignored nested folders or loose files.
    const folderName=parts.length===3?parts[1]:parts.length===2?parts[0]:null
    if(!folderName||parts.some(part=>!part||part==='.'||part==='..')){
      errors.push({path:relative,reason:'Нужна папка конструкции непосредственно внутри выбранной библиотеки'})
      continue
    }
    const construction=parseConstructionFolder(folderName)
    if(!construction){
      errors.push({path:relative,reason:'Неправильное имя папки. Пример: SAM 0004 — Гагарина 64'})
      continue
    }
    const existing=folders.get(construction.sam)
    if(existing&&existing.address!==construction.address){
      errors.push({path:relative,reason:'Один номер конструкции указан с разными адресами'})
      continue
    }
    if(!ALLOWED.test(file.name)){
      errors.push({path:relative,reason:'Неподдерживаемый тип файла'})
      continue
    }
    if(file.size===0){
      errors.push({path:relative,reason:'Пустой файл'})
      continue
    }
    if(file.size>MAX_IMAGE_UPLOAD_BYTES){
      errors.push({path:relative,reason:'Размер превышает 60 МБ'})
      continue
    }
    const group=existing||construction
    group.count++
    folders.set(group.sam,group)
    totalBytes+=file.size
    tasks.push({sam:construction.sam,address:construction.address,
      entry:{file,relative}})
  }
  return {tasks,folders:[...folders.values()],errors,scanned,totalBytes}
}
