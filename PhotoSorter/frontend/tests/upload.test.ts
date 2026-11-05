import {parseConstructionFolder,inspectReferenceDirectory} from '../src/utils/referenceSelection'
import {indexReferenceHashes,fileSha256} from '../src/utils/referenceDuplicates'
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest'
import {directoryEntries,ALLOWED,UPLOAD_CHUNK_BYTES,uploadOne} from '../src/utils/upload'
import {runUploadQueue} from '../src/utils/uploadQueue'
import {normalizeParallelUploads} from '../src/stores/uploadSettings'

const saved=new Map<string,string>()
beforeEach(()=>{
  saved.clear()
  vi.stubGlobal('localStorage',{
    getItem:(key:string)=>saved.get(key)??null,
    setItem:(key:string,value:string)=>{saved.set(key,value)},
    removeItem:(key:string)=>{saved.delete(key)}
  })
})
afterEach(()=>vi.unstubAllGlobals())

describe('folder input',()=>{
  it('accepts only supported image extensions',()=>{
    expect(ALLOWED.test('IMG_001.JPG')).toBe(true)
    expect(ALLOWED.test('file.jpeg')).toBe(true)
    expect(ALLOWED.test('image.png')).toBe(true)
    expect(ALLOWED.test('video.mp4')).toBe(false)
    expect(ALLOWED.test('archive.zip')).toBe(false)
  })
  it('rejects empty folder',()=>{
    expect(()=>directoryEntries({length:0} as FileList)).toThrow('не найдено')
  })
})

describe('resumable upload transport',()=>{
  it('uses PATCH chunks of 16 MiB, never direct PUT, for a new photo',async()=>{
    const chunkSizes:number[]=[]
    let offset=0
    const fetch=vi.fn(async(url:string,opts:RequestInit={})=>{
      if(url==='/api/uploads'&&opts.method==='POST')
        return Response.json({id:'new-id'})
      if(url==='/api/uploads/new-id'&&opts.method==='PATCH'){
        const chunk=opts.body as Blob
        expect(opts.headers).toBeInstanceOf(Headers)
        chunkSizes.push(chunk.size)
        expect((opts.headers as Headers).get('upload-offset')).toBe(String(offset))
        offset+=chunk.size
        return Response.json({offset})
      }
      if(url==='/api/uploads/new-id/finish'&&opts.method==='POST')
        return Response.json({path:'/uploaded/image.jpg'})
      throw Error('Unexpected '+opts.method+' '+url)
    })
    vi.stubGlobal('fetch',fetch)
    const file=new File([new Uint8Array(UPLOAD_CHUNK_BYTES+9)],'image.jpg')
    const progress:number[]=[]
    const result=await uploadOne({kind:'fo',batchId:'batch-a'},{file,relative:'folder/image.jpg'},
      new AbortController().signal,n=>progress.push(n))
    expect(result.path).toBe('/uploaded/image.jpg')
    expect(chunkSizes).toEqual([UPLOAD_CHUNK_BYTES,9])
    expect(progress.at(-1)).toBe(file.size)
    expect(fetch.mock.calls.some(([,opts])=>opts?.method==='PUT')).toBe(false)
    expect(saved.values().next().value).toBe('done')
  })
  it('resumes a previously started transfer from server offset',async()=>{
    const file=new File([new Uint8Array(UPLOAD_CHUNK_BYTES+5)],'resume.jpg')
    saved.set('ps.up.v3.fo:batch-a:folder/resume.jpg:'+file.size+':'+file.lastModified,'existing-id')
    const chunks:number[]=[]
    const fetch=vi.fn(async(url:string,opts:RequestInit={})=>{
      if(url==='/api/uploads/existing-id'&&!opts.method)
        return Response.json({id:'existing-id',offset:UPLOAD_CHUNK_BYTES,size:file.size,finalized:false})
      if(url==='/api/uploads/existing-id'&&opts.method==='PATCH'){
        chunks.push((opts.body as Blob).size)
        expect((opts.headers as Headers).get('upload-offset')).toBe(String(UPLOAD_CHUNK_BYTES))
        return Response.json({offset:file.size})
      }
      if(url==='/api/uploads/existing-id/finish'&&opts.method==='POST')
        return Response.json({path:'/uploaded/resume.jpg'})
      throw Error('Unexpected '+opts.method+' '+url)
    })
    vi.stubGlobal('fetch',fetch)
    await uploadOne({kind:'fo',batchId:'batch-a'},{file,relative:'folder/resume.jpg'},
      new AbortController().signal,()=>{})
    expect(chunks).toEqual([5])
    expect(fetch.mock.calls.some(([url])=>url==='/api/uploads')).toBe(false)
  })
})

describe('parallel upload scheduling',()=>{
  it('defaults to 5 and rejects invalid concurrency settings',()=>{
    expect(normalizeParallelUploads(null)).toBe(5)
    expect(normalizeParallelUploads('5')).toBe(5)
    expect(normalizeParallelUploads('10')).toBe(10)
    expect(normalizeParallelUploads('11')).toBe(5)
    expect(normalizeParallelUploads('0')).toBe(5)
  })
  it('never exceeds configured concurrent uploads',async()=>{
    let inFlight=0,peak=0
    const completed:number[]=[]
    const failures=await runUploadQueue(12,5,new AbortController().signal,async index=>{
      inFlight++
      peak=Math.max(peak,inFlight)
      await Promise.resolve()
      completed.push(index)
      inFlight--
    })
    expect(failures).toEqual([])
    expect(peak).toBe(5)
    expect(completed).toHaveLength(12)
  })
  it('continues other files after a failure, but reports it',async()=>{
    const completed:number[]=[]
    const failures=await runUploadQueue(4,3,new AbortController().signal,async index=>{
      if(index===1)throw Error('network error')
      completed.push(index)
    })
    expect(completed.sort()).toEqual([0,2,3])
    expect(failures).toHaveLength(1)
    expect(failures[0]?.index).toBe(1)
  })
  it('stops scheduling after abort',async()=>{
    const controller=new AbortController()
    const started:number[]=[]
    await expect(runUploadQueue(20,1,controller.signal,async index=>{
      started.push(index)
      controller.abort()
    })).rejects.toMatchObject({name:'AbortError'})
    expect(started).toEqual([0])
  })
})

describe('upload outage visibility',()=>{
  it('reports errors immediately and stops an unavailable server before 1330 attempts',async()=>{
    const started:number[]=[]
    const errors:number[]=[]
    await expect(runUploadQueue(1330,5,new AbortController().signal,async index=>{
      started.push(index)
      throw new Error('HTTP 500')
    },{
      haltAfterFailuresWithoutSuccess:3,
      onFailure:failure=>errors.push(failure.index)
    })).rejects.toThrow('Передача остановлена')
    expect(errors.length).toBeGreaterThanOrEqual(3)
    expect(errors[0]).toBe(0)
    expect(started.length).toBeLessThan(10) // Existing workers may launch next item before halt
  })
  it('continues valid uploads when one image fails after progress',async()=>{
    const done:number[]=[]
    const failures=await runUploadQueue(7,3,new AbortController().signal,async index=>{
      if(index===2)throw new Error('invalid image')
      done.push(index)
    },{haltAfterFailuresWithoutSuccess:3})
    expect(done).toHaveLength(6)
    expect(failures.map(f=>f.index)).toEqual([2])
  })
})

describe('strict construction library imports',()=>{
  function file(path:string,name:string,contents='photo'){
    const image=new File([contents],name)
    Object.defineProperty(image,'webkitRelativePath',{value:path})
    return image
  }
  it('accepts the strict city, number and address without losing leading zeros',()=>{
    expect(parseConstructionFolder('SAM 0004 — Гагарина 64')).toMatchObject({
      sam:'SAM 0004',number:'0004',address:'Гагарина 64'
    })
    expect(parseConstructionFolder('TLT 01 — Ленина 25')?.sam).toBe('TLT 01')
    expect(parseConstructionFolder('SAM-0004 — Гагарина 64')).toBeNull()
    expect(parseConstructionFolder('SAM 0004 - Гагарина 64')).toBeNull()
    expect(parseConstructionFolder('SAM 0004')).toBeNull()
  })
  it('accounts for every file and reports forbidden folders, nested paths and formats',()=>{
    const result=inspectReferenceDirectory([
      file('Образцы/SAM 0004 — Гагарина 64/a.jpg','a.jpg'),
      file('Образцы/SAM 0004 — Гагарина 64/b.png','b.png'),
      file('Образцы/TLT 3245 — Южное шоссе 10/c.jpg','c.jpg'),
      file('Образцы/SAM-0005/invalid.jpg','invalid.jpg'),
      file('Образцы/SAM 0004 — Гагарина 64/notes.txt','notes.txt'),
      file('Образцы/SAM 0004 — Гагарина 64/nested/x.jpg','x.jpg')
    ])
    expect(result.scanned).toBe(6)
    expect(result.tasks).toHaveLength(3)
    expect(result.errors).toHaveLength(3)
    expect(result.tasks.length+result.errors.length).toBe(result.scanned)
    expect(result.folders).toHaveLength(2)
    expect(result.folders.find(x=>x.sam==='SAM 0004')?.count).toBe(2)
  })
  it('rejects conflicting addresses for the same city and construction number',()=>{
    const result=inspectReferenceDirectory([
      file('Образцы/SAM 003 — Полевая 10/a.jpg','a.jpg'),
      file('Образцы/SAM 003 — Полевая 12/b.jpg','b.jpg')
    ])
    expect(result.errors).toHaveLength(1)
    expect(result.folders).toHaveLength(1)
    expect(result.tasks).toHaveLength(1)
  })
})

describe('reference duplicate detection before transfer',()=>{
  it('keeps hashes scoped to one construction, independent of filenames',()=>{
    const hash='a'.repeat(64)
    const index=indexReferenceHashes([{id:'1',sam:'SAM 0004',name:'old.jpg',sha256:hash}])
    expect(index.get('SAM 0004')?.has(hash)).toBe(true)
    expect(index.has('TLT 0004')).toBe(false)
  })
  it('hashes actual file bytes with SHA-256 when browser crypto is available',async()=>{
    const digest=await fileSha256(new File(['abc'],'new.jpg'))
    if(typeof crypto!=='undefined'&&crypto.subtle){
      expect(digest).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    }else{
      expect(digest).toBeNull()
    }
  })
})
