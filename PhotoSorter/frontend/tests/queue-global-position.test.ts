import {describe,it,expect} from 'vitest'
import {estimateQueue} from '../src/utils/queueEstimates'
import {readyToStart,runLabel} from '../src/utils/format'
import type {QueueTask} from '../src/types/workQueue'

const task=(seq:number,position:number):QueueTask=>({
  seq,queue_position:position,kind:'fo_processing',state:'queued',
  fo_run_id:'run-'+seq,fo_photo_count:100,reference_job_id:null,session_id:null,
  created_at:'2026-11-26T12:00:00Z',started_at:null,finished_at:null,
  total_count:null,completed_count:null,failed_count:null,error:null,
  stop_requested:null,batch_id:null,batch_name:null,fo_source:null
})
describe('global FIFO position',()=>{
  it('does not predict a start or finish from a filtered queue',()=>{
    const history={...task(1,1),state:'completed' as const,
      started_at:'2026-11-26T11:00:00Z',finished_at:'2026-11-26T11:01:00Z'}
    const own=[task(3,3),task(4,4),task(5,5)]
    const estimates=estimateQueue(own,[history])
    for(const item of own){
      expect(estimates.get(item.seq)?.startInSeconds).toBeNull()
      expect(estimates.get(item.seq)?.finishInSeconds).toBeNull()
    }
    expect(estimateQueue([task(3,1)],[history]).get(3)?.startInSeconds).toBe(0)
  })
  it('does not mistake first place for worker readiness',()=>{
    expect(readyToStart({status:'queued',queue_position:1})).toBe(false)
    expect(runLabel({status:'queued',queue_position:2})).toBe('В очереди №2')
  })
})
