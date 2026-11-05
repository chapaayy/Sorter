import {describe,it,expect} from 'vitest'
import type {Batch} from '../src/types/api'
import {canProcessBatch,canResumeUpload} from '../src/utils/batches'

function batch(overrides:Partial<Batch>={}):Batch{
  return {
    batch_id:'eab92e09-7786-4534-82f0-122c99904f10',
    display_name:'Новая папка ФО',created_at:'2026-11-05T12:00:00Z',
    upload_state:'ready',thumbnail_state:'pending',delete_state:'active',
    photos:5,size_bytes:1024,pending:0,...overrides
  }
}

describe('batch eligibility with empty history and deleted tombstones',()=>{
  it('offers a newly uploaded batch even if old API omitted runs',()=>{
    expect(canProcessBatch(batch({runs:undefined}))).toBe(true)
    expect(canResumeUpload(batch({runs:undefined}))).toBe(true)
    expect(canResumeUpload(batch({runs:0}))).toBe(true)
  })
  it('allows reprocessing finished batches, but not resuming their original upload',()=>{
    expect(canProcessBatch(batch({runs:1}))).toBe(true)
    expect(canResumeUpload(batch({runs:1}))).toBe(false)
  })
  it('does not offer unfinished, empty or deleting batches',()=>{
    expect(canProcessBatch(batch({pending:1}))).toBe(false)
    expect(canProcessBatch(batch({photos:0}))).toBe(false)
    expect(canProcessBatch(batch({delete_state:'deleting'}))).toBe(false)
    expect(canResumeUpload(batch({delete_state:'deleted'}))).toBe(false)
  })
})
