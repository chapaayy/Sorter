import type {RunProgress} from './api'
export type QueueKind='fo_processing'|'reference_preparation'
export type QueueStatus='queued'|'running'|'blocked'|'completed'|'completed_with_errors'|'stopped'|'failed'|'interrupted'
export interface QueueTask {
  seq:number
  kind:QueueKind
  fo_run_id:string|null
  reference_job_id:string|null
  session_id:string|null
  state:QueueStatus
  created_at:string
  started_at:string|null
  finished_at:string|null
  total_count:number|null
  completed_count:number|null
  failed_count:number|null
  error:string|null
  stop_requested:boolean|null
  batch_id:string|null
  batch_name:string|null
  fo_source:string|null
  fo_progress?:RunProgress|null
  fo_photo_count?:number|null
  fo_thumbnail_url?:string|null
}
export interface PreparationError {
  upload_id:string
  detail:string
  occurred_at:string
}
export interface PreparationDetail {
  id:string
  session_id:string
  state:string
  total_count:number
  completed_count:number
  failed_count:number
  error:string|null
  queue_seq:number
  stop_requested:boolean
  errors:PreparationError[]
}
