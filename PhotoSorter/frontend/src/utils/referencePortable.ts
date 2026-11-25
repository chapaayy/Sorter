/** Map optional portable manifest to the same upload tasks as directory import. */
import {inspectReferenceDirectory,parseConstructionFolder} from './referenceSelection'
import type {PortableConstruction,ReferenceSelection,ConstructionFolder,ReferenceUploadTask} from './referenceSelection'
import {ALLOWED,MAX_IMAGE_UPLOAD_BYTES} from './upload'
const MAX_MANIFEST=32*1024**2
const meta=new Set(['thumbs.db','ehthumbs.db','desktop.ini','.ds_store'])
const safe=(value:unknown):value is string=>typeof value==='string'&&!!value&&value.length<=1024&&value.split('/').every(p=>!!p&&p!=='.'&&p!=='..'&&!/[\\<>:"|?*\x00-\x1f]/.test(p))
const fail=(message:string):never=>{throw new Error('Манифест образцов: '+message)}
type Obj=Record<string,unknown>
function object(value:unknown):Obj{
  if(!value||typeof value!=='object'||Array.isArray(value))return fail('неверная запись')
  return value as Obj
}
function text(value:unknown,max:number):string{
  if(typeof value!=='string'||!value||value.length>max)return fail('некорректное текстовое поле')
  return value
}
function nullable(value:unknown,max:number){return value===null?null:text(value,max)}
export async function inspectPortableSelection(files:File[],signal:AbortSignal):Promise<ReferenceSelection>{
  const relative=(f:File)=>f.webkitRelativePath||f.name
  const manifest=files.filter(f=>f.name==='manifest.json'&&relative(f).split('/').length<=2)
  if(!manifest.length)return inspectReferenceDirectory(files)
  if(manifest.length!==1||manifest[0].size>MAX_MANIFEST)return fail('повтор или слишком большой файл')
  const mf=manifest[0],prefix=relative(mf).slice(0,-mf.name.length)
  const parsed=object(JSON.parse(await mf.text()))
  signal.throwIfAborted()
  if(parsed.schema!=='map-reference-library-v1'||!Array.isArray(parsed.constructions)||!Array.isArray(parsed.photos)
    ||!parsed.constructions.length||parsed.constructions.length>5000||parsed.photos.length>20000)return fail('неподдерживаемая схема или размер')
  const catalog:PortableConstruction[]=[],folders:ConstructionFolder[]=[],tasks:ReferenceUploadTask[]=[]
  const bySam=new Map<string,{folder:ConstructionFolder;directory:string;item:PortableConstruction}>()
  const dirs=new Set<string>(),paths=new Map<string,File>(),seen=new Set<string>()
  const skipped:ReferenceSelection['skipped']=[{path:relative(mf),reason:'Манифест библиотеки'}]
  for(const value of parsed.constructions){
    const row=object(value),sam=text(row.sam,80),directory=text(row.directory,250)
    const kind=row.kind,city_code=nullable(row.city_code,5),number=nullable(row.number,8),address=nullable(row.address,120)
    if(!safe(directory)||directory.includes('/')||bySam.has(sam)||dirs.has(directory.normalize('NFC').toLowerCase())||!(kind==='standard'||kind==='custom'))return fail('некорректная конструкция: '+sam)
    if(kind==='standard'){
      const standard=parseConstructionFolder(sam+' — '+address)
      if(!address||!standard||standard.cityCode!==city_code||standard.number!==number)return fail('некорректный адрес: '+sam)
    }else if(city_code!==null||number!==null||address!==null)return fail('некорректная индивидуальная конструкция: '+sam)
    const item:PortableConstruction={sam,kind,city_code,number,address}
    const folder={folder:kind==='standard'?sam+' — '+address:sam,sam,cityCode:city_code||'',number:number||'',address:address||'',count:0}
    bySam.set(sam,{folder,directory,item});dirs.add(directory.normalize('NFC').toLowerCase());catalog.push(item);folders.push(folder)
  }
  for(const file of files){
    if(file===mf)continue
    const rel=relative(file)
    if(!rel.startsWith(prefix)||!safe(rel))return fail('небезопасный путь: '+rel)
    const path=rel.slice(prefix.length)
    if(meta.has(file.name.toLowerCase())){skipped.push({path:rel,reason:'Служебный файл ОС'});continue}
    if(paths.has(path)||!path)return fail('повтор файла: '+path)
    paths.set(path,file)
  }
  let totalBytes=0
  for(const [index,value] of parsed.photos.entries()){
    const row=object(value),path=text(row.path,1024),sam=text(row.sam,80),name=text(row.filename,200),sha=text(row.sha256,64),side=nullable(row.side,60)
    const entry=bySam.get(sam),file=paths.get(path)
    if(!safe(path)||path.split('/').length!==3||path.split('/')[0]!==entry?.directory||!file||seen.has(path)||!ALLOWED.test(name)||!safe(name)||name.includes('/')
      ||!ALLOWED.test(file.name)||!file.size||file.size>MAX_IMAGE_UPLOAD_BYTES||file.size!==row.size||!/^[a-f0-9]{64}$/.test(sha))return fail('фото или размер не совпадает: '+path)
    const sideFolder=path.split('/')[1]
    if((side===null&&sideFolder!=='Неназначенные')||(side!==null&&/^[AB][1-3]?$/.test(side)&&sideFolder!==side)
      ||(side!==null&&!/^[AB][1-3]?$/.test(side)&&!sideFolder.startsWith('Историческая сторона')))return fail('сторона не совпадает с путём: '+path)
    seen.add(path)
    const original=file.name===name?file:new File([file],name,{lastModified:0})
    // Original names can collide after undoing ZIP's portable suffixes.
    const uploadPath=file.name===name?path:'portable/'+index+'/'+name
    tasks.push({sam,address:entry.item.address||undefined,side,portable:true,expectedSha256:sha,entry:{file:original,relative:uploadPath}})
    entry.folder.count++;totalBytes+=file.size
  }
  if(seen.size!==paths.size)return fail('есть фотографии вне манифеста')
  return {tasks,folders,catalog,errors:[],skipped,scanned:files.length,totalBytes}
}
