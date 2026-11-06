import {describe,it,expect} from 'vitest'
import type {Batch,Run} from '../src/types/api'
import {batchProcessing,batchThreshold} from '../src/utils/batchProcessing'

const base:Batch={
  batch_id:'09be06a2-444e-4e51-8b62-de1c672f2cfe',
  display_name:'ФО ноябрь',created_at:'2026-11-05T08:00:00Z',
  delete_state:'active',upload_state:'ready',thumbnail_state:'ready',
  photos:100,pending:0,runs:0,size_bytes:1024,upload_manifest_state:'complete'
}
function batch(overrides:Partial<Batch>={}):Batch{return {...base,...overrides}}
function run(status:string,more:Partial<Run>={}):Run{
  return {id:'20261105T000000-aaaaaaaaaaaa',batch_id:base.batch_id,status,
    grouping_threshold:.7,...more}
}
describe('true MegaLoc state on FO cards',()=>{
  it('does not equate ready thumbnails with successful processing',()=>{
    const s=batchProcessing(batch())
    expect(s.label).toBe('Не обработано')
    expect(s.tone).toBe('neutral')
    expect(s.canStart).toBe(true)
    expect(s.resultId).toBeNull()
  })
  it('blocks incomplete manifests even when pending=0',()=>{
    const s=batchProcessing(batch({upload_manifest_state:'waiting',pending:0}))
    expect(s.label).toBe('Загрузка не завершена')
    expect(s.canStart).toBe(false)
  })
  it('shows genuine queued position and stop action',()=>{
    const s=batchProcessing(batch({latest_run:run('queued',{queue_position:7}),runs:1}))
    expect(s.label).toBe('В очереди')
    expect(s.detail).toContain('7')
    expect(s.canStop).toBe(true)
    expect(s.canStart).toBe(false)
    expect(s.tone).toBe('neutral')
  })
  it('uses measured running progress; never invents missing percentages',()=>{
    const s=batchProcessing(batch({latest_run:run('running',{progress:{
      stage_label:'Группировка',current:17,total:90,
      overall_percent:21.2,stage_percent:42.5}}),runs:1}))
    expect(s.overallPercent).toBe(21.2)
    expect(s.stagePercent).toBe(42.5)
    expect(s.stageCounts).toBe('17 из 90 на этапе')
    const noMetrics=batchProcessing(batch({latest_run:run('running'),runs:1}))
    expect(noMetrics.overallPercent).toBeNull()
    expect(noMetrics.stagePercent).toBeNull()
  })
  it('only fully completed status is green, failed retry retains earlier results',()=>{
    expect(batchProcessing(batch({latest_run:run('completed'),runs:1})).tone).toBe('ok')
    expect(batchProcessing(batch({latest_run:run('completed_with_errors'),runs:1})).tone).toBe('danger')
    const s=batchProcessing(batch({latest_run:run('failed',{error:'Missing model'}),
      last_result_run_id:'prior-success',runs:2}))
    expect(s.tone).toBe('danger')
    expect(s.resultId).toBe('prior-success')
    expect(s.canStart).toBe(true)
    expect(batchThreshold(batch({latest_run:run('failed')}))).toBe(.7)
    expect(batchProcessing(batch({latest_run:run('stopped'),runs:1})).tone).toBe('neutral')
  })
  it('lets pending automatic jobs be cancelled without falsely calling them completed',()=>{
    const s=batchProcessing(batch({latest_run:null,auto_process_state:'waiting'}))
    expect(s.label).toBe('Ожидает автозапуска')
    expect(s.canCancelAuto).toBe(true)
    expect(s.tone).toBe('neutral')
  })
  it('never offers run controls for deleting batches',()=>{
    const s=batchProcessing(batch({delete_state:'deleting',latest_run:run('queued'),runs:1}))
    expect(s.canStart).toBe(false)
    expect(s.canStop).toBe(false)
  })
  it('does not call a legacy batch with history unprocessed without latest_run',()=>{
    const s=batchProcessing(batch({runs:2,latest_run:undefined}))
    expect(s.label).toBe('Есть история запусков')
  })
})
