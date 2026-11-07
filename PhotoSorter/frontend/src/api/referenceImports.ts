/** Typed staged-reference import API. Intentionally not connected to the UI yet.
 * Enabled only when the shared FIFO worker is ready (stage 3).
 */
import {api,post,query} from './client'

export type ImportFileState='pending'|'finalized'|'duplicate'|'missing_saved'
export type ImportUploadState='uploading'|'complete'|'cancelled'
export type ReferencePrepState='pending'|'queued'|'running'|'completed'|'failed'|'stopped'|'interrupted'
export interface ReferenceImportFile{
  upload_id:string
  sam:string
  relative_path:string
  filename:string
  size:number
  state:ImportFileState
  received:number
  sha256:string|null
}
export interface ReferenceImportStatus{
  id:string
  state:ImportUploadState
  preparation_state:ReferencePrepState
  expected:number
  registered:boolean
  finalized:number
  duplicates:number
  missing:number
  pending:number
  completed_at:string|null
  preparation_job_id:string|null
  queue_seq:number|null
  files:ReferenceImportFile[]
}
export interface ManifestFile{
  upload_id:string
  sam:string
  address?:string|null
  relative_path:string
  filename:string
  size:number
  sha256?:string|null
}
export interface TransferOffset{
  upload_id:string
  state:ImportFileState
  offset:number
  size:number
  sha256:string|null
}
export interface Completion{session_id:string;preparation_job_id:string;queue_seq:number;state:'queued'}
export interface ImportSessionSummary{
  id:string
  state:ImportUploadState
  preparation_state:ReferencePrepState
  expected_count:number|null
  created_at:string
  completed_at:string|null
  preparation_job_id:string|null
  total_count:number|null
  completed_count:number|null
  failed_count:number|null
  finalized:number
  duplicates:number
  queue_seq:number|null
  error:string|null
}
export const referenceImportsApi={
  list:(limit=25,offset=0)=>api<{sessions:ImportSessionSummary[];total:number}>(
    '/reference-imports'+query({limit,offset})),
  create:(client_session_id:string)=>post<ReferenceImportStatus>('/reference-imports',{client_session_id}),
  register:(id:string,files:ManifestFile[])=>api<ReferenceImportStatus>(
    '/reference-imports/'+encodeURIComponent(id)+'/manifest',
    {method:'PUT',body:JSON.stringify({files})}),
  status:(id:string)=>api<ReferenceImportStatus>('/reference-imports/'+encodeURIComponent(id)),
  file:(id:string,upload_id:string)=>api<TransferOffset>(
    '/reference-imports/'+encodeURIComponent(id)+'/files/'+encodeURIComponent(upload_id)),
  append:(id:string,upload_id:string,offset:number,bytes:Uint8Array,signal?:AbortSignal)=>
    api<{offset:number}>('/reference-imports/'+encodeURIComponent(id)+'/files/'+encodeURIComponent(upload_id),
      {method:'PATCH',headers:{'upload-offset':String(offset),'Content-Type':'application/octet-stream'},
       body:new Blob([bytes as BlobPart]),signal}),
  finish:(id:string,upload_id:string)=>post<{sha256:string;already_finalized?:boolean;already_present?:boolean}>(
    '/reference-imports/'+encodeURIComponent(id)+'/files/'+encodeURIComponent(upload_id)+'/finish',{}),
  duplicate:(id:string,upload_id:string,sha256:string)=>post<{sha256:string;already_present:boolean}>(
    '/reference-imports/'+encodeURIComponent(id)+'/files/'+encodeURIComponent(upload_id)+'/duplicate',{sha256}),
  complete:(id:string)=>post<Completion>('/reference-imports/'+encodeURIComponent(id)+'/complete',{})
}
