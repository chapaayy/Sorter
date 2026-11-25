/** Read ZIP from local Blob slices; never expand an archive into server storage. */
import {MAX_IMAGE_UPLOAD_BYTES} from './upload'
const MAX_ENTRIES=100000,MAX_CENTRAL=64*1024**2,MAX_MANIFEST=32*1024**2
const MAX_INFLATED=512*1024**2
const decoder=new TextDecoder('utf-8',{fatal:true})
const bad=(reason:string):never=>{throw new Error('ZIP: '+reason)}
const view=(b:ArrayBuffer)=>new DataView(b)
const u16=(v:DataView,o:number)=>v.getUint16(o,true)
const u32=(v:DataView,o:number)=>v.getUint32(o,true)
function u64(v:DataView,o:number){
  const n=Number(v.getBigUint64(o,true))
  if(!Number.isSafeInteger(n))bad('слишком большое смещение')
  return n
}
async function read(file:Blob,offset:number,size:number){
  if(offset<0||size<0||!Number.isSafeInteger(offset+size)||offset+size>file.size)bad('выход за границы архива')
  return view(await file.slice(offset,offset+size).arrayBuffer())
}
function nameOf(v:DataView,start:number,length:number,flags:number){
  const bytes=new Uint8Array(v.buffer,v.byteOffset+start,length)
  if(!(flags&0x800)&&bytes.some(x=>x>=128))bad('неподдерживаемая кодировка имён; используйте UTF-8')
  let path=''
  try{path=decoder.decode(bytes)}catch{bad('некорректное имя UTF-8')}
  const parts=path.replace(/\/$/,'').split('/')
  if(!path||path.length>1024||parts.some(p=>!p||p==='.'||p==='..'||/[\\<>:"|?*\x00-\x1f]/.test(p)))bad('небезопасный путь: '+path)
  return path
}
function extended(v:DataView,start:number,length:number,size:number,packed:number,offset:number){
  const needs=[size===0xffffffff,packed===0xffffffff,offset===0xffffffff]
  if(!needs.some(Boolean))return [size,packed,offset]
  let at=start
  while(at+4<=start+length){
    const tag=u16(v,at),n=u16(v,at+2);at+=4
    if(at+n>start+length)bad('повреждённое дополнительное поле')
    if(tag===1){
      let i=at
      const values=[size,packed,offset].map((x,k)=>{
        if(!needs[k])return x
        if(i+8>at+n)bad('неполное ZIP64 поле')
        const value=u64(v,i);i+=8;return value
      })
      return values
    }
    at+=n
  }
  return bad('нет ZIP64 поля')
}
const crcTable=Uint32Array.from({length:256},(_,i)=>{
  let n=i
  for(let j=0;j<8;j++)n=n&1?0xedb88320^(n>>>1):n>>>1
  return n>>>0
})
export async function zipCrc(blob:Blob,signal:AbortSignal){
  let crc=0xffffffff
  const reader=blob.stream().getReader()
  try{
    while(true){
      signal.throwIfAborted()
      const {done,value}=await reader.read()
      if(done)break
      for(const byte of value)crc=crcTable[(crc^byte)&255]^(crc>>>8)
    }
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
  return (crc^0xffffffff)>>>0
}
async function inflate(blob:Blob,size:number,signal:AbortSignal){
  if(typeof DecompressionStream==='undefined')return bad('этот браузер не поддерживает распаковку; выберите папку')
  const reader=blob.stream().pipeThrough(new DecompressionStream('deflate-raw')).getReader()
  const chunks:BlobPart[]=[]
  let total=0
  try{
    while(true){
      signal.throwIfAborted()
      const {done,value}=await reader.read()
      if(done)break
      total+=value.byteLength
      if(total>size)bad('распакованный размер превышает заявленный')
      chunks.push(new Uint8Array(value))
    }
    if(total!==size)bad('неверный распакованный размер')
    return new Blob(chunks)
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
}
type Entry={path:string;flags:number;method:number;crc:number;size:number;packed:number;offset:number;directory:boolean}
export async function readReferenceZip(file:Blob,signal:AbortSignal,onProgress=(done:number,total:number)=>{}):Promise<File[]>{
  const tailSize=Math.min(file.size,65557),tailStart=file.size-tailSize
  const tail=await read(file,tailStart,tailSize)
  let end=-1
  for(let i=tailSize-22;i>=0;i--)if(u32(tail,i)===0x06054b50&&i+22+u16(tail,i+20)===tailSize){end=i;break}
  if(end<0)bad('не найден конец центрального каталога')
  if(u16(tail,end+4)||u16(tail,end+6)||u16(tail,end+8)!==u16(tail,end+10))bad('многотомный архив не поддерживается')
  let count=u16(tail,end+10),centralSize=u32(tail,end+12),centralOffset=u32(tail,end+16)
  let boundary=tailStart+end
  if(count===0xffff||centralSize===0xffffffff||centralOffset===0xffffffff){
    const locator=await read(file,boundary-20,20)
    if(u32(locator,0)!==0x07064b50||u32(locator,4)!==0||u32(locator,16)!==1)bad('некорректный ZIP64 locator')
    const pos=u64(locator,8),record=await read(file,pos,56)
    if(u32(record,0)!==0x06064b50||u32(record,16)||u32(record,20)||u64(record,24)!==u64(record,32)||pos+12+u64(record,4)!==boundary-20)bad('некорректный ZIP64 каталог')
    count=u64(record,32);centralSize=u64(record,40);centralOffset=u64(record,48);boundary=pos
  }
  if(!count||count>MAX_ENTRIES||centralSize>MAX_CENTRAL||centralOffset+centralSize!==boundary)bad('неверный размер каталога или слишком много записей')
  const cd=await read(file,centralOffset,centralSize),entries:Entry[]=[]
  const names=new Set<string>()
  let at=0,totalInflated=0,photoCount=0
  for(let i=0;i<count;i++){
    signal.throwIfAborted()
    if(at+46>centralSize||u32(cd,at)!==0x02014b50)bad('повреждённый центральный каталог')
    const flags=u16(cd,at+8),method=u16(cd,at+10),n=u16(cd,at+28),extra=u16(cd,at+30),comment=u16(cd,at+32)
    const next=at+46+n+extra+comment
    if(next>centralSize||u16(cd,at+34)!==0||flags&~0x080e||![0,8].includes(method))bad('шифрование, многотомность или неподдерживаемый метод')
    const path=nameOf(cd,at+46,n,flags),directory=path.endsWith('/')
    const mode=(u32(cd,at+38)>>>16)&0xf000
    if(mode&&mode!==(directory?0x4000:0x8000))bad('ссылка или специальный файл: '+path)
    const key=path.replace(/\/$/,'').normalize('NFC').toLowerCase()
    if(names.has(key))bad('повтор имени: '+path)
    names.add(key)
    const [size,packed,offset]=extended(cd,at+46+n,extra,u32(cd,at+24),u32(cd,at+20),u32(cd,at+42))
    if(directory?(size!==0||packed!==0&&method===0):(!size||size>(path.endsWith('manifest.json')?MAX_MANIFEST:MAX_IMAGE_UPLOAD_BYTES)))bad('недопустимый размер: '+path)
    if(!directory&&++photoCount>20001)bad('более 20000 фотографий и манифеста')
    if(method===0&&size!==packed)bad('несовпадение размеров STORED')
    if(method===8&&(totalInflated+=size)>MAX_INFLATED)bad('более 512 МиБ распакованных данных DEFLATE; распакуйте ZIP на компьютере и выберите папку')
    entries.push({path,flags,method,crc:u32(cd,at+16),size,packed,offset,directory});at=next
  }
  if(at!==centralSize)bad('лишние данные в центральном каталоге')
  const spans:{start:number;end:number}[]=[],files:File[]=[]
  const regular=new Set(entries.filter(e=>!e.directory).map(e=>e.path.normalize('NFC').toLowerCase()))
  for(const [i,e] of entries.entries()){
    signal.throwIfAborted();onProgress(i,entries.length)
    const parts=e.path.replace(/\/$/,'').split('/')
    for(let j=1;j<parts.length;j++)if(regular.has(parts.slice(0,j).join('/').normalize('NFC').toLowerCase()))bad('файл используется как каталог')
    const local=await read(file,e.offset,30)
    if(u32(local,0)!==0x04034b50||u16(local,6)!==e.flags||u16(local,8)!==e.method)bad('несовпадение локального заголовка')
    const n=u16(local,26),extra=u16(local,28),header=await read(file,e.offset+30,n+extra)
    if(nameOf(header,0,n,e.flags)!==e.path)bad('несовпадение имени записи')
    if(!(e.flags&8)){
      const [size,packed]=extended(header,n,extra,u32(local,22),u32(local,18),0)
      if(size!==e.size||packed!==e.packed||u32(local,14)!==e.crc)bad('несовпадение размеров или CRC заголовков')
    }
    const start=e.offset+30+n+extra,finish=start+e.packed
    if(finish>centralOffset||!Number.isSafeInteger(finish))bad('запись выходит за границы данных')
    spans.push({start:e.offset,end:finish})
    if(e.directory)continue
    if(!/\.(jpe?g|png|webp|bmp|tiff?)$/i.test(e.path)&&!/(^|\/)(manifest\.json|thumbs\.db|ehthumbs\.db|desktop\.ini|\.ds_store)$/i.test(e.path))bad('неподдерживаемый файл: '+e.path)
    const packed=file.slice(start,finish)
    const blob=e.method===0?packed:await inflate(packed,e.size,signal)
    if(await zipCrc(blob,signal)!==e.crc)bad('CRC не совпадает: '+e.path)
    const image=new File([blob],parts[parts.length-1]!,{lastModified:0})
    Object.defineProperty(image,'webkitRelativePath',{value:e.path})
    files.push(image)
  }
  spans.sort((a,b)=>a.start-b.start)
  for(let i=1;i<spans.length;i++)if(spans[i].start<spans[i-1].end)bad('пересекающиеся записи')
  onProgress(entries.length,entries.length)
  return files
}
