import type {Batch} from '../types/api'

// Completed runs are allowed; the backend prevents simultaneous runs.
export function canProcessBatch(batch:Batch):boolean{
  return batch.delete_state==='active' && (batch.photos??0)>0 && (batch.pending??0)===0
}

// Older responses omitted the 'runs' key on never-processed batches.
export function canResumeUpload(batch:Batch):boolean{
  return batch.delete_state==='active' && (batch.runs??0)===0
}
