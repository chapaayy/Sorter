import {describe,it,expect} from 'vitest'
import {FaviconState,type OwnTask,type OwnWorkStatus} from '../src/utils/faviconState'
const before='2026-11-26T18:00:00Z',after='2026-11-26T18:00:05Z'
function task(state:OwnTask['state'],run_id='run-a',progress:number|null=null,finished_at:string|null=null):OwnTask{
  return {seq:1,run_id,state,progress,finished_at}
}
const snapshot=(...tasks:OwnTask[]):OwnWorkStatus=>({account_id:'1',sampled_at:before,tasks})
describe('personal favicon status',()=>{
  it('does not replay historical results when a session starts',()=>{
    const f=new FaviconState()
    expect(f.update(snapshot(task('completed','old',100,before)))).toEqual({kind:'idle'})
    expect(f.update(snapshot(task('failed','older',null,before)))).toEqual({kind:'idle'})
  })
  it('shows overall progress, never success before confirmed terminal state',()=>{
    const f=new FaviconState()
    expect(f.update(snapshot(task('running','run-a',100)))).toEqual({kind:'running',run:'run-a',progress:1})
    expect(f.update(snapshot(task('completed','run-a',100,after),task('queued','run-b')))).toEqual({kind:'queued'})
    expect(f.update(snapshot(task('running','run-b',null)))).toEqual({kind:'running',run:'run-b',progress:null})
    expect(f.update(snapshot(task('completed','run-b',100,after)))).toEqual({kind:'success'})
    f.acknowledgeSuccess()
    expect(f.state()).toEqual({kind:'idle'})
    expect(f.update(snapshot(task('completed','run-b',100,after)))).toEqual({kind:'idle'})
  })
  it('keeps an error through another active run, and acknowledges only the matching run',()=>{
    const f=new FaviconState()
    f.update(snapshot(task('running')))
    expect(f.update(snapshot(task('failed','run-a',null,after),task('running','run-b',55)))).toEqual({kind:'running',run:'run-b',progress:.55})
    expect(f.update(snapshot(task('completed_with_errors','run-b',100,after)))).toEqual({kind:'error'})
    f.acknowledgeRun('run-a')
    expect(f.state()).toEqual({kind:'error'})
    f.acknowledgeHistory()
    expect(f.state()).toEqual({kind:'idle'})
  })
  it('stopped work is not a successful completion and fresh sessions start clean',()=>{
    const f=new FaviconState()
    f.update(snapshot(task('running')))
    expect(f.update(snapshot(task('stopped','run-a',null,after)))).toEqual({kind:'paused'})
    expect(new FaviconState().state()).toEqual({kind:'idle'})
  })
  it('does not infer success when a run disappears',()=>{
    const f=new FaviconState();f.update(snapshot(task('running')))
    expect(f.update(snapshot())).toEqual({kind:'idle'})
  })
})
