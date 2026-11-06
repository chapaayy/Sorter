import {api,post,patch,del,query} from './client'
import type {Batch,Photo,CursorPage,Retention,PendingUploadList} from '../types/api'
export const batchApi={
  list:(limit=100,offset=0)=>api<{batches:Batch[];total:number}>('/batches'+query({limit,offset})),
  one:(id:string)=>api<Batch>('/batches/'+encodeURIComponent(id)),
  pending:(id:string)=>api<PendingUploadList>('/batches/'+encodeURIComponent(id)+'/pending'),
  finishPending:(uploadId:string)=>api<{path:string;already_finalized?:boolean}>('/uploads/'+encodeURIComponent(uploadId)+'/finish',{method:'POST'}),
  cancelPending:(uploadId:string)=>del<{cancelled:boolean}>('/uploads/'+encodeURIComponent(uploadId)),
  create:(name:string)=>post<{batch_id:string;display_name:string}>('/batches',{display_name:name}),
  rename:(id:string,name:string)=>patch<Batch>('/batches/'+id,{display_name:name}),
  gallery:(id:string,cursor?:string|null,limit=60)=>api<CursorPage<Photo>>('/batches/'+id+'/gallery'+query({cursor,limit})),
  removePhoto:(id:string,pid:string)=>del<{deleted:boolean}>('/batches/'+id+'/photos/'+pid),
  remove:(id:string)=>del<{state:string}>('/batches/'+id),
  deletion:(id:string)=>api<{state:string}>('/batches/'+id+'/deletion'),
  thumbs:(id:string)=>api<{total:number;ready:number;failed:number}>('/thumbnails/status/'+id+'/counts'),
  retention:(id:string)=>api<Retention>('/batches/'+id+'/retention'),
  confirm:(id:string,runId:string)=>post<Retention>('/batches/'+id+'/downloads/confirm',{run_id:runId}),
  extend:(id:string)=>post<Retention>('/batches/'+id+'/retention/extend',{})
}
