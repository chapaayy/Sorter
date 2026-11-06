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
  it('constructs same-origin archive URL without source paths',()=>{
    expect(resultApi.download('20261105T000000-abcdef123456','SAM-0001')).toBe('/api/download/20261105T000000-abcdef123456?sam=SAM-0001')
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
