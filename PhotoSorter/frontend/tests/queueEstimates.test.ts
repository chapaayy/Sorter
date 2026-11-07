import {describe,it,expect} from 'vitest'
import {estimateQueue,historicalRates,queueTime,runTime,actualDuration,approxDuration}
  from '../src/utils/queueEstimates'
import type {QueueTask} from '../src/types/workQueue'

const now=Date.parse('2026-11-07T12:00:00Z')
function entry(seq:number,kind:QueueTask['kind'],state:QueueTask['state'],count:number):QueueTask{
  return {seq,kind,state,created_at:'2026-11-07T10:00:00Z',
    started_at:null,finished_at:null,
    fo_run_id:kind==='fo_processing'?'fo-'+seq:null,
    reference_job_id:kind==='reference_preparation'?'prep-'+seq:null,
    session_id:null,total_count:kind==='reference_preparation'?count:null,
    completed_count:0,failed_count:0,error:null,stop_requested:false,
    batch_id:null,batch_name:null,fo_source:null,
    fo_photo_count:kind==='fo_processing'?count:null}
}
const historyFO=(seq:number,seconds:number,count=100)=>{
  const task=entry(seq,'fo_processing','completed',count)
  task.started_at=new Date(now-seconds*1000).toISOString()
  task.finished_at=new Date(now).toISOString()
  return task
}
const historyPrep=(seq:number,seconds:number,count=10)=>{
  const task=entry(seq,'reference_preparation','completed',count)
  task.started_at=new Date(now-seconds*1000).toISOString()
  task.finished_at=new Date(now).toISOString()
  return task
}
describe('measured FIFO time projections',()=>{
  it('does not fabricate future ETA before any measured examples exist',()=>{
    const active=[entry(1,'fo_processing','queued',100),
      entry(2,'reference_preparation','queued',50)]
    const predictions=estimateQueue(active,[],now)
    expect(predictions.get(1)?.startInSeconds).toBe(0)
    expect(predictions.get(1)?.finishInSeconds).toBeNull()
    expect(predictions.get(2)?.finishInSeconds).toBeNull()
    expect(queueTime(active[1],predictions.get(2)).detail).toBe('Время уточняется')
  })
  it('counts running FO plus EVERY preceding FO and reference preparation',()=>{
    const current=entry(1,'fo_processing','running',150)
    current.started_at=new Date(now-180000).toISOString()
    current.fo_progress={estimated_remaining_seconds:120,overall_percent:60,
      stage_label:'MegaLoc'}
    const second=entry(2,'fo_processing','queued',100)
    const third=entry(3,'reference_preparation','queued',20)
    const fourth=entry(4,'fo_processing','queued',50)
    const map=estimateQueue([fourth,third,current,second],
      [historyFO(10,200),historyPrep(11,30)],now)
    expect(map.get(1)?.remainingSeconds).toBe(120)
    expect(map.get(2)).toMatchObject({startInSeconds:120,durationSeconds:200,finishInSeconds:320})
    expect(map.get(3)).toMatchObject({startInSeconds:320,durationSeconds:60,finishInSeconds:380})
    expect(map.get(4)).toMatchObject({startInSeconds:380,durationSeconds:100,finishInSeconds:480})
    expect(queueTime(second,map.get(2)).label).toBe('≈ 6 мин')
    expect(queueTime(second,map.get(2)).detail).toBe('Старт ≈ 2 мин')
  })
  it('does not invent estimates when the running task has no ETA',()=>{
    const first=entry(1,'fo_processing','running',100)
    first.started_at=new Date(now-120000).toISOString()
    const queued=entry(2,'fo_processing','queued',100)
    const value=estimateQueue([first,queued],[historyFO(3,200)],now)
    expect(value.get(2)?.startInSeconds).toBeNull()
    expect(value.get(2)?.finishInSeconds).toBeNull()
  })
  it('blocks all downstream time estimates after failed preparation',()=>{
    const failed=entry(1,'reference_preparation','failed',10)
    const waiting=entry(2,'fo_processing','queued',100)
    const value=estimateQueue([failed,waiting],[historyFO(3,200)],now)
    expect(value.get(2)?.finishInSeconds).toBeNull()
  })
  it('separates actual duration and historic medians by work type',()=>{
    const rates=historicalRates([historyFO(2,200),historyFO(3,400),
      historyFO(4,300),historyPrep(5,90)])
    expect(rates.fo_processing).toBe(3)
    expect(rates.reference_preparation).toBe(9)
    const start='2026-11-07T09:00:00Z',end='2026-11-07T09:01:05Z'
    expect(actualDuration(start,end)).toBe('1 мин 5 с')
    expect(actualDuration(start)).toBe('—')
    expect(runTime({id:'x',batch_id:'b',status:'completed',
      actual_started_at:start,actual_finished_at:end}).label).toBe('За 1 мин 5 с')
    expect(approxDuration(null)).toBe('—')
    expect(approxDuration(61)).toBe('≈ 2 мин')
  })
})
