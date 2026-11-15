import type {Batch} from '../types/api'

// Completed runs are allowed; the backend prevents simultaneous runs.
export function canProcessBatch(batch:Batch):boolean{
  return batch.delete_state==='active' && ((batch.photos??0)+(batch.videos??0))>0 &&
    !['queued','running','interrupted','failed'].includes(batch.media_preparation?.state??'') && (batch.pending??0)===0 &&
    (batch.upload_manifest_state==null||batch.upload_manifest_state==='complete')
}
