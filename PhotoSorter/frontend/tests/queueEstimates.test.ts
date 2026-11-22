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
  it('shows historical full-run ETA when backend projection is partial',()=>{
    const current=entry(1,'fo_processing','running',150)
    current.started_at=new Date(now-60_000).toISOString()
    current.fo_progress={stage:'queries',current:10,total:150,
      stage_items_per_second:2,estimated_remaining_seconds:null,eta_status:'partial'}
    const map=estimateQueue([current],[historyFO(10,300,150)],now)
    expect(map.get(1)).toMatchObject({
      remainingSeconds:240,finishInSeconds:240,basis:'history'
    })
    expect(queueTime(current,map.get(1))).toEqual({
      label:'≈ 4 мин',detail:'По прошлым ФО'
    })
  })
  it('shows an honest stage ETA when no whole-run measurement exists',()=>{
    const current=entry(1,'fo_processing','running',647)
    current.started_at=new Date(now-120_000).toISOString()
    current.fo_progress={stage:'queries',current:20,total:647,
      stage_items_per_second:1.5,estimated_remaining_seconds:null,
      eta_status:'partial'}
    const queued=entry(2,'fo_processing','queued',100)
    const map=estimateQueue([current,queued],[],now)
    expect(map.get(1)?.basis).toBe('stage')
    expect(map.get(1)?.remainingSeconds).toBeCloseTo(418,5)
    expect(map.get(1)?.finishInSeconds).toBeNull()
    expect(queueTime(current,map.get(1))).toEqual({
      label:'≈ 7 мин',detail:'До конца этапа'
    })
    expect(map.get(2)?.startInSeconds).toBeNull()
    expect(map.get(2)?.finishInSeconds).toBeNull()
    expect(runTime({id:'r',batch_id:'b',status:'running',
      progress:current.fo_progress}).detail).toBe('До конца этапа')
  })
  it('does not show a stage rate before enough samples or a zero rate',()=>{
    const current=entry(1,'fo_processing','running',100)
    current.started_at=new Date(now-1000).toISOString()
    current.fo_progress={stage:'queries',current:2,total:100,stage_items_per_second:12}
    let map=estimateQueue([current],[],now)
    expect(map.get(1)?.remainingSeconds).toBeNull()
    current.fo_progress={stage:'queries',current:10,total:100,stage_items_per_second:0}
    map=estimateQueue([current],[],now)
    expect(map.get(1)?.remainingSeconds).toBeNull()
  })
  it('keeps authoritative backend run ETA ahead of historical and stage rates',()=>{
    const current=entry(1,'fo_processing','running',150)
    current.started_at=new Date(now-60_000).toISOString()
    current.fo_progress={stage:'queries',current:20,total:150,
      stage_items_per_second:.01,estimated_remaining_seconds:95,eta_status:'measured'}
    const map=estimateQueue([current],[historyFO(10,600,150)],now)
    expect(map.get(1)?.remainingSeconds).toBe(95)
    expect(map.get(1)?.basis).toBe('measured')
    expect(map.get(1)?.finishInSeconds).toBe(95)
    expect(queueTime(current,map.get(1)).detail).toBe('Осталось')
  })
  it('refuses an optimistic history ETA shorter than the measured current stage',()=>{
    const current=entry(1,'fo_processing','running',100)
    current.started_at=new Date(now-10_000).toISOString()
    current.fo_progress={stage:'queries',current:5,total:100,
      stage_items_per_second:1,estimated_remaining_seconds:null}
    const map=estimateQueue([current],[historyFO(10,30,100)],now)
    expect(map.get(1)?.basis).toBe('stage')
    expect(map.get(1)?.remainingSeconds).toBe(95)
    expect(map.get(1)?.finishInSeconds).toBeNull()
  })

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
  it('falls back to historical whole-run time when there is no backend ETA',()=>{
    const first=entry(1,'fo_processing','running',100)
    first.started_at=new Date(now-120000).toISOString()
    const queued=entry(2,'fo_processing','queued',100)
    const value=estimateQueue([first,queued],[historyFO(3,200)],now)
    expect(value.get(1)?.basis).toBe('history')
    expect(value.get(1)?.remainingSeconds).toBe(80)
    expect(value.get(2)?.startInSeconds).toBe(80)
    expect(value.get(2)?.finishInSeconds).toBe(280)
  })
  it('uses remaining seconds for the whole conversion in FIFO',()=>{
    const current={...entry(1,'media_preparation','running',2),media_eta_seconds:36}
    const next=entry(2,'fo_processing','queued',100)
    const map=estimateQueue([current,next],[historyFO(3,200)],now)
    expect(map.get(1)?.remainingSeconds).toBe(36)
    expect(queueTime(current,map.get(1))).toEqual({label:'≈ 36 с',detail:'Осталось'})
    expect(map.get(2)?.startInSeconds).toBe(36)
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
