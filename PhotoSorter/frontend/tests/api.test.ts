import {describe,it,expect,vi,afterEach} from 'vitest'
import {api,query} from '../src/api/client'
import {batchApi} from '../src/api/batches'
import {runApi} from '../src/api/runs'
import {referenceApi} from '../src/api/references'
import {resultApi} from '../src/api/results'
import {logApi} from '../src/api/logs'
afterEach(()=>vi.unstubAllGlobals())
describe('typed API contracts',()=>{
  it('encodes URL parameter values',()=>{
    const q=query({cursor:'a+/=',sam:'SAM-0123-A',limit:60,unset:undefined})
    expect(q).toContain('cursor=a%2B%2F%3D')
    expect(q).not.toContain('unset')
  })
  it('preserves HTTP error details and same-origin cookies',async()=>{
    const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'Busy'}),{status:409,headers:{'content-type':'application/json'}}))
    vi.stubGlobal('fetch',fetch)
    await expect(api('/runs')).rejects.toMatchObject({status:409,message:'Busy'})
    expect(fetch.mock.calls[0]?.[1]?.credentials).toBe('same-origin')
  })
  it('persists automatic processing preferences through the existing authenticated API',async()=>{
    const fetch=vi.fn(async(_url:string,opts:RequestInit)=>new Response(JSON.stringify({auto_process_new_batches:false,grouping_threshold:.50,model:'megaloc'}),{status:200,headers:{'content-type':'application/json'}}))
    vi.stubGlobal('fetch',fetch)
    await runApi.saveAutoSettings(false,.50)
    const call=fetch.mock.calls[0]
    expect(call[0]).toBe('/api/processing-settings')
    expect(call[1].method).toBe('PATCH')
    expect(JSON.parse(String(call[1].body))).toEqual({auto_process_new_batches:false,grouping_threshold:.50})
  })
  it('uses backward-compatible filtered run lists for live and historical views',async()=>{
    const urls:string[]=[]
    vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>{
      urls.push(url)
      return new Response(JSON.stringify({runs:[],total:0}),{
        status:200,headers:{'content-type':'application/json'}})
    }))
    await runApi.active()
    await runApi.history(30,60)
    await runApi.list(20,0)
    expect(urls[0]).toContain('scope=active')
    expect(urls[0]).toContain('limit=25')
    expect(urls[1]).toContain('scope=history')
    expect(urls[1]).toContain('offset=60')
    expect(urls[2]).not.toContain('scope=')
  })
  it('edits all construction fields through an encoded PATCH route',async()=>{
    const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({
      sam:'TLT 0042',previous_sam:'SAM 0001',changed:true,kind:'standard'
    }),{status:200,headers:{'content-type':'application/json'}}))
    vi.stubGlobal('fetch',fetch)
    const payload={kind:'standard' as const,city_code:'TLT',number:'0042',address:'Мира 9'}
    await referenceApi.updateConstruction('SAM 0001',payload)
    expect(fetch.mock.calls[0]?.[0]).toBe('/api/references/constructions/SAM%200001')
    expect(fetch.mock.calls[0]?.[1]?.method).toBe('PATCH')
    expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toEqual(payload)
  })
  it('constructs same-origin archive URL without source paths',()=>{
    expect(resultApi.download('20261105T000000-abcdef123456','SAM-0001')).toBe('/api/download/20261105T000000-abcdef123456?sam=SAM-0001')
    expect(referenceApi.downloadAll()).toBe('/api/references/export')
  })
  it('requests cursor pages and log tail from the correct routes',async()=>{
    const urls:string[]=[]
    vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>{
      urls.push(url)
      return new Response(JSON.stringify({photos:[],next_cursor:'next'}),{status:200,headers:{'content-type':'application/json'}})
    }))
    await batchApi.gallery('abcd','foo',60)
    await referenceApi.gallery('SAM-0001','foo')
    await logApi.page('run',{tail_mode:true,limit:200})
    expect(urls[0]).toContain('/batches/abcd/gallery')
    expect(urls[1]).toContain('/references/SAM-0001/photos')
    expect(urls[2]).toContain('tail_mode=true')
  })
})
