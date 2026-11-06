import {describe,it,expect} from 'vitest'
import type {Run} from '../src/types/api'
import {orderedQueue,activeInference,canRequestStop,runDuration,runStat} from '../src/utils/processingDashboard'

const base={batch_id:'f939d4ee-ff55-413d-977a-c987ab74e898',
  grouping_threshold:.50}
const job=(id:string,status:string,more:Partial<Run>={}):Run=>({id,status,...base,...more})

describe('MegaLoc dashboard never invents state',()=>{
  it('isolates and sorts queued runs by server-provided queue positions',()=>{
    const runs=[
      job('z','queued',{queue_position:3}),
      job('x','completed'),job('b','queued',{queue_position:1}),
      job('a','queued',{queue_position:2})
    ]
    expect(orderedQueue(runs).map(r=>r.id)).toEqual(['b','a','z'])
  })
  it('shows running and stopping separately from queued',()=>{
    expect(activeInference([job('a','queued')])).toBeNull()
    expect(activeInference([job('a','queued'),job('b','running')])?.id).toBe('b')
    expect(activeInference([job('b','stopping')])?.status).toBe('stopping')
  })
  it('only offers stop for jobs that can still be newly stopped',()=>{
    expect(canRequestStop(job('a','queued'))).toBe(true)
    expect(canRequestStop(job('a','running'))).toBe(true)
    for(const state of ['stopping','completed','failed','interrupted','stopped'])
      expect(canRequestStop(job('a',state))).toBe(false)
  })
  it('does not fabricate durations or per-model photo counts',()=>{
    expect(runDuration(job('a','completed'))).toBe('—')
    expect(runDuration(job('a','completed',{actual_started_at:'2026-11-05T00:00:00Z',
      actual_finished_at:'2026-11-05T00:01:05Z'}))).toBe('1 мин 5 с')
    expect(runDuration(job('a','completed',{actual_started_at:'2026-11-05T00:01:00Z',
      actual_finished_at:'2026-11-05T00:00:00Z'}))).toBe('—')
    expect(runStat(undefined)).toBe('—')
    expect(runStat(0)).toBe('0')
    expect(runStat(-1)).toBe('—')
  })
})
