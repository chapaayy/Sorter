import {afterEach,describe,expect,it,vi} from 'vitest'
import {libraryNoticesApi} from '../src/api/libraryNotices'
import {referenceImportsApi} from '../src/api/referenceImports'

afterEach(()=>vi.unstubAllGlobals())
function respond(value:unknown){
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({
    ok:true,status:200,json:async()=>value
  }))
}
describe('stage 4 server-authoritative API',()=>{
  it('only a deliberate POST acknowledges the published version',async()=>{
    respond({notice:true,notice_version_id:13})
    await libraryNoticesApi.status()
    expect(vi.mocked(fetch)).toHaveBeenCalledWith('/api/reference-library/status',expect.anything())
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.method).not.toBe('POST')
    await libraryNoticesApi.acknowledge(13)
    const call=vi.mocked(fetch).mock.calls[1]!
    expect(call[0]).toBe('/api/reference-library/notices/ack')
    expect(call[1]?.method).toBe('POST')
    expect(call[1]?.body).toBe(JSON.stringify({version_id:13}))
  })
  it('fetches only the server-owned staging session list',async()=>{
    respond({sessions:[],total:0})
    await referenceImportsApi.list(10)
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      '/api/reference-imports?limit=10&offset=0',expect.anything())
  })
})
