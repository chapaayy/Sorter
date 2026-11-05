/** Preview the entire directory selection BEFORE uploading any references.
 * Keep SAM parsing equivalent to app/photos/labels.py on the server.
 */
import {ALLOWED,MAX_IMAGE_UPLOAD_BYTES} from './upload'
import type {UploadEntry} from './upload'

export interface ReferenceUploadTask{sam:string;entry:UploadEntry}
export interface ReferenceSelection{
  tasks:ReferenceUploadTask[]
  scanned:number
  unsupported:number
  missingSam:number
  empty:number
  tooLarge:number
  unrecognizedFolders:string[]
  unsupportedExtensions:string[]
}

const SAM_NUMBER=/^SAM-\d{4}(?!\d)/i
const SAM_SIDE=/^-([ABCDАБВГ]\d{0,2})(?=$|[-\s,;.(])/i
const SAM_PANEL=/^-([PР]\d{1,2})(?=$|[-\s,;.(])/i

/** A valid folder such as "SAM-0004 Ленина" resolves to "SAM-0004".
 * Sides and panels remain part of the SAM identifier as in the backend.
 */
export function samFromFolder(folder:string):string|null{
  const base=SAM_NUMBER.exec(folder)
  if(!base)return null
  let tail=folder.slice(base[0].length)
  if(tail&&!/^[- ,;\t\r\n(]/.test(tail))return null
  let result=base[0].toUpperCase()
  const side=SAM_SIDE.exec(tail)
  if(side){result+='-'+side[1].toUpperCase();tail=tail.slice(side[0].length)}
  const panel=SAM_PANEL.exec(tail)
  if(panel)result+='-'+panel[1].toUpperCase()
  return result
}

export function inspectReferenceDirectory(files:Iterable<File>):ReferenceSelection{
  const tasks:ReferenceUploadTask[]=[]
  const unknown=new Set<string>(),extensions=new Set<string>()
  let scanned=0,unsupported=0,missingSam=0,empty=0,tooLarge=0
  for(const file of files){
    scanned++
    const relative=file.webkitRelativePath||file.name
    const segments=relative.replace(/\\/g,'/').split('/').filter(Boolean)
    // Only a directory may identify a SAM; a filename containing SAM-xxxx does not.
    const folders=segments.slice(0,-1)
    let sam:string|null=null
    for(const folder of folders){sam=samFromFolder(folder);if(sam)break}
    if(!sam){
      missingSam++
      if(unknown.size<12)unknown.add(folders.join('/')||'(без папки)')
      continue
    }
    if(!ALLOWED.test(file.name)){
      unsupported++
      if(extensions.size<12)extensions.add(file.name.includes('.')?file.name.slice(file.name.lastIndexOf('.')).toLowerCase():'(без расширения)')
      continue
    }
    if(file.size===0){empty++;continue}
    if(file.size>MAX_IMAGE_UPLOAD_BYTES){tooLarge++;continue}
    tasks.push({sam,entry:{file,relative}})
  }
  return {tasks,scanned,unsupported,missingSam,empty,tooLarge,
    unrecognizedFolders:[...unknown],unsupportedExtensions:[...extensions]}
}
