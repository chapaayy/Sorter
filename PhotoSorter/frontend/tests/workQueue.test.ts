import {describe,it,expect} from 'vitest'
import {duration,hasBlockingFailure,queuePosition,STATE_RU} from '../src/utils/queuePresentation'
import type {QueueTask} from '../src/types/workQueue'

const task=(seq:number,kind:QueueTask['kind'],state:QueueTask['state']):QueueTask=>({
  seq,kind,state,fo_run_id:kind==='fo_processing'?'run-'+seq:null,
  reference_job_id:kind==='reference_preparation'?'prep-'+seq:null,
  session_id:null,created_at:'2026-11-07T09:00:00Z',
  started_at:null,finished_at:null,total_count:null,completed_count:null,
  failed_count:null,error:null,stop_requested:null,batch_id:null,
  batch_name:null,fo_source:null
})
describe('single FIFO queue presentation',()=>{
  it('positions tasks by database seq, never by task type',()=>{
    const entries=[task(7,'fo_processing','queued'),
      task(6,'reference_preparation','queued'),task(2,'fo_processing','queued')]
    expect(queuePosition(entries,2)).toBe(1)
    expect(queuePosition(entries,6)).toBe(2)
    expect(queuePosition(entries,7)).toBe(3)
  })
  it('failed preparation remains a blocking dependency, failed FO does not',()=>{
    expect(hasBlockingFailure(task(4,'reference_preparation','failed'))).toBe(true)
    expect(hasBlockingFailure(task(4,'reference_preparation','interrupted'))).toBe(true)
    expect(hasBlockingFailure(task(4,'reference_preparation','stopped'))).toBe(false)
    expect(hasBlockingFailure(task(5,'fo_processing','failed'))).toBe(false)
    expect(STATE_RU.running).toBe('Выполняется')
  })
  it('shows factual run duration without made-up estimates',()=>{
    expect(duration(task(1,'fo_processing','queued'))).toBe('—')
    const running=task(1,'reference_preparation','running')
    running.started_at='2026-11-07T10:00:00Z'
    expect(duration(running,new Date('2026-11-07T10:26:00Z').getTime())).toBe('26 мин')
    running.finished_at='2026-11-07T11:15:00Z'
    expect(duration(running)).toBe('1 ч 15 мин')
  })
})
