import {createPinia,setActivePinia} from 'pinia'
import {beforeEach,describe,expect,it,vi} from 'vitest'
import {useUploadCenterStore} from '../src/stores/uploadCenter'
import {createFoTransfer} from '../src/utils/foTransfer'
import type {UploadContext,UploadResult,UploadSource} from '../src/types/uploadQueue'

vi.mock('../src/utils/foTransfer',()=>({createFoTransfer:vi.fn(),transferRecovery:vi.fn()}))
vi.mock('../src/stores/notice',()=>({useNoticeStore:()=>({add:vi.fn()})}))

const selection=(name:string):UploadSource=>({
  kind:'fo',name,entries:[],autoProcess:false,threshold:.5
})
function deferred(){
  let resolve!:(value:UploadResult)=>void,reject!:(error:Error)=>void
  const promise=new Promise<UploadResult>((yes,no)=>{resolve=yes;reject=no})
  return {promise,resolve,reject}
}
beforeEach(()=>{
  setActivePinia(createPinia())
  vi.mocked(createFoTransfer).mockReset()
})

describe('website transfer queue',()=>{
  it('blocks later rows while pausing and paused; starts the next after cancellation',async()=>{
    const first=deferred(),resumed=deferred(),second=deferred()
    const contexts:UploadContext[]=[]
    const initial=vi.fn<(context:UploadContext)=>Promise<UploadResult>>()
      .mockImplementationOnce(context=>{contexts.push(context);return first.promise})
      .mockImplementationOnce(context=>{contexts.push(context);return resumed.promise})
    vi.mocked(createFoTransfer)
      .mockReturnValueOnce(initial)
      .mockReturnValueOnce(context=>{contexts.push(context);return second.promise})
    const store=useUploadCenterStore()
    store.enqueue(selection('321'))
    store.enqueue(selection('322'))
    store.enqueue(selection('323'))
    const id=store.current!.id
    expect(contexts).toHaveLength(1)
    store.pause(id)
    expect(contexts[0]?.signal.aborted).toBe(true)
    expect(store.current?.status).toBe('pausing')
    expect(store.rows.map(row=>row.status)).toEqual(['pausing','waiting','waiting'])
    first.reject(new Error('aborted'))
    await vi.waitFor(()=>expect(store.current?.status).toBe('paused'))
    expect(contexts).toHaveLength(1)
    store.cancel(store.rows.at(-1)!.id)
    store.continueUpload(id)
    // The same runner holds the same resumable batch identity.
    expect(contexts).toHaveLength(2)
    store.cancel(id)
    expect(store.current?.status).toBe('cancelling')
    expect(store.rows).toHaveLength(2)
    expect(contexts[1]?.signal.aborted).toBe(true)
    resumed.reject(new Error('aborted'))
    await vi.waitFor(()=>expect(store.current?.name).toBe('322'))
    expect(contexts).toHaveLength(3)
    expect(store.current?.status).toBe('running')
    second.resolve({message:'saved'})
    await vi.waitFor(()=>expect(store.rows).toHaveLength(0))
  })

  it('leaves a failed transfer at the head and retries it before advancing',async()=>{
    const first=deferred()
    const runner=vi.fn<(_:UploadContext)=>Promise<UploadResult>>()
      .mockReturnValueOnce(first.promise).mockResolvedValue({message:'saved'})
    const next=vi.fn(async()=>({message:'saved'}))
    vi.mocked(createFoTransfer).mockReturnValueOnce(runner).mockReturnValueOnce(next)
    const store=useUploadCenterStore()
    store.enqueue(selection('321'))
    store.enqueue(selection('322'))
    first.reject(new Error('Ошибка передачи'))
    await vi.waitFor(()=>expect(store.current?.status).toBe('failed'))
    expect(store.current?.error).toBe('Ошибка передачи')
    expect(next).not.toHaveBeenCalled()
    store.continueUpload(store.current!.id)
    await vi.waitFor(()=>expect(store.rows).toHaveLength(0))
    expect(runner).toHaveBeenCalledTimes(2)
    expect(next).toHaveBeenCalledTimes(1)
  })
})
