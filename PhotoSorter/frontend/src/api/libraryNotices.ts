import {api,post,query} from './client'
export interface LibraryStatus {
  unified_queue_enabled:boolean
  staged_imports_enabled:boolean
  current_version_id:number|null
  current_version:number|null
  published_at:string|null
  published_references:number
  baseline_state:'pending'|'ready'|'needs_attention'
  baseline_error:string|null
  last_fo_uploaded_at:string|null
  last_fo_upload_version_id:number|null
  acknowledged_version_id:number|null
  pending_changes:number
  notice_version_id:number|null
  notice:boolean
  message:string
}
export interface LibraryEvent {
  id:number
  version_id:number
  version_number:number
  event_kind:string
  actor:string
  details:Record<string,unknown>
  created_at:string
}
export const libraryNoticesApi={
  status:()=>api<LibraryStatus>('/reference-library/status'),
  events:(limit=30,afterVersion?:number|null)=>
    api<{events:LibraryEvent[]}>('/reference-library/events'+
      query({limit,after_version:afterVersion})),
  acknowledge:(version_id:number)=>post<LibraryStatus>(
    '/reference-library/notices/ack',{version_id})
}
