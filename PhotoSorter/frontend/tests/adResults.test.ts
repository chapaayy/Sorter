import {afterEach,describe,expect,it,vi} from 'vitest'
import {adResultsApi} from '../src/api/adResults'
import {isResultView,resultViews} from '../src/types/resultViews'
afterEach(()=>vi.unstubAllGlobals())

describe('Stage 4 saved-result navigation and typed API',()=>{
  it('exposes all seven standalone result modes',()=>{
    expect(resultViews).toEqual(['sam','group','screens','visual-groups','ads','ocr','comparisons'])
    expect(resultViews.length).toBe(new Set(resultViews).size)
    expect(isResultView('comparisons')).toBe(true)
    expect(isResultView('unexpected')).toBe(false)
  })
  it('pages saved XFeat, DINO rankings, layout photos and OCR without write requests',async()=>{
    const urls:string[]=[]
    const methods:string[]=[]
    vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string,opts:RequestInit)=>{
      urls.push(url);methods.push(opts.method||'GET')
      return new Response('{}',{headers:{'content-type':'application/json'}})
    }))
    const run='20261108T120000-123abc123abc'
    await adResultsApi.screens(run,'next=cursor',24)
    await adResultsApi.visualGroups(run,50,50)
    await adResultsApi.rankings(run,'R0007',{limit:30,offset:60,index:12,screen_id:'screen-uuid'})
    await adResultsApi.textGroups(run,{layout_id:'some-layout',limit:25})
    await adResultsApi.photos(run,'unidentified',{best_only:true,limit:32,subgroup_id:'T0001'})
    await adResultsApi.ocr(run,'cursor/with+',24)
    expect(urls).toHaveLength(6)
    expect(urls[0]).toContain('/api/ad-results/runs/'+run+'/screens?')
    expect(urls[0]).toContain('cursor=next%3Dcursor')
    expect(urls[1]).toContain('offset=50')
    expect(urls[2]).toContain('screen_id=screen-uuid')
    expect(urls[3]).toContain('layout_id=some-layout')
    expect(urls[4]).toContain('best_only=true')
    expect(urls[4]).toContain('subgroup_id=T0001')
    expect(urls[5]).toContain('cursor=cursor%2Fwith%2B')
    expect(methods).toEqual(Array(6).fill('GET'))
  })
  it('uses pinned, run-specific historical advertising-layout URLs',()=>{
    expect(adResultsApi.layoutImage('run-1','layout-id')).toBe(
      '/api/ad-results/runs/run-1/layouts/layout-id/image')
  })
})
