import {describe,it,expect} from 'vitest'
import {readReferenceZip,zipCrc} from '../src/utils/referenceZip'
import {inspectPortableSelection} from '../src/utils/referencePortable'
import {deflateRawSync} from 'node:zlib'

async function fixture(path:string,data:Uint8Array,method=0,corrupt=false){
  const name=new TextEncoder().encode(path),packed=method?new Uint8Array(deflateRawSync(data)):data
  const crc=await zipCrc(new Blob([new Uint8Array(data)]),new AbortController().signal)
  const local=new Uint8Array(30+name.length+packed.length),l=new DataView(local.buffer)
  l.setUint32(0,0x04034b50,true);l.setUint16(4,20,true);l.setUint16(6,0x800,true);l.setUint16(8,method,true)
  l.setUint32(14,crc,true);l.setUint32(18,packed.length,true);l.setUint32(22,data.length,true);l.setUint16(26,name.length,true)
  local.set(name,30);local.set(packed,30+name.length)
  if(corrupt)local[30+name.length]^=1
  const central=new Uint8Array(46+name.length),c=new DataView(central.buffer)
  c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint16(8,0x800,true);c.setUint16(10,method,true)
  c.setUint32(16,crc,true);c.setUint32(20,packed.length,true);c.setUint32(24,data.length,true);c.setUint16(28,name.length,true)
  central.set(name,46)
  const end=new Uint8Array(22),e=new DataView(end.buffer)
  e.setUint32(0,0x06054b50,true);e.setUint16(8,1,true);e.setUint16(10,1,true)
  e.setUint32(12,central.length,true);e.setUint32(16,local.length,true)
  return new Blob([local,central,end])
}
const signal=()=>new AbortController().signal
describe('reference ZIP reader',()=>{
  it.each([0,8])('reads method %i and retains paths',async method=>{
    const data=new TextEncoder().encode('test photo')
    const result=await readReferenceZip(await fixture('SAM 0004 — Гагарина 64/B2/a.jpg',data,method),signal())
    expect(result[0].webkitRelativePath).toBe('SAM 0004 — Гагарина 64/B2/a.jpg')
    expect(await result[0].text()).toBe('test photo')
    expect((await inspectPortableSelection(result,signal())).tasks[0].side).toBe('B2')
  })
  it('rejects traversal and corrupt data',async()=>{
    const data=new TextEncoder().encode('abc')
    await expect(readReferenceZip(await fixture('../a.jpg',data),signal())).rejects.toThrow('небезопасный путь')
    await expect(readReferenceZip(await fixture('a.jpg',data,0,true),signal())).rejects.toThrow('CRC')
  })
  it('uses portable catalog and exact metadata, rejects unlisted photos',async()=>{
    const path='Custom/B2/a (2).jpg',file=new File(['abc'],'a (2).jpg')
    Object.defineProperty(file,'webkitRelativePath',{value:path})
    const manifest=new File([JSON.stringify({schema:'map-reference-library-v1',
      constructions:[{sam:'Custom',directory:'Custom',kind:'custom',city_code:null,number:null,address:null},
      {sam:'SAM 0004',directory:'SAM 0004 — Гагарина 64',kind:'standard',city_code:'SAM',number:'0004',address:'Гагарина 64'}],
      photos:[{path,sam:'Custom',filename:'a.jpg',sha256:'a'.repeat(64),size:3,side:'B2'}]})],'manifest.json')
    const selection=await inspectPortableSelection([manifest,file],signal())
    expect(selection.catalog?.length).toBe(2)
    expect(selection.tasks[0]).toMatchObject({sam:'Custom',side:'B2',expectedSha256:'a'.repeat(64)})
    expect(selection.tasks[0].entry.file.name).toBe('a.jpg')
    await expect(inspectPortableSelection([manifest,file,new File(['b'],'extra.jpg')],signal())).rejects.toThrow('вне манифеста')
  })
})
