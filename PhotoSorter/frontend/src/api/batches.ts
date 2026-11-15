import {api,post,patch,del,query} from './client'
import type {Batch,DeletionProgress,Photo,CursorPage,Retention,PendingUploadList,BatchUploadManifest,UploadManifestFile,Run} from '../types/api'
export const batchApi={
  list:(limit=100,offset=0)=>api<{batches:Batch[];total:number}>('/batches'+query({limit,offset})),
  one:(id:string)=>api<Batch>('/batches/'+encodeURIComponent(id)),
  runs:(id:string,limit=20,offset=0)=>api<{runs:Run[];total:number}>(
    '/batches/'+encodeURIComponent(id)+'/runs'+query({limit,offset})),
  pending:(id:string)=>api<PendingUploadList>('/batches/'+encodeURIComponent(id)+'/pending'),
  manifest:(id:string)=>api<BatchUploadManifest>('/batches/'+encodeURIComponent(id)+'/upload-manifest'),
  registerManifest:(id:string,files:UploadManifestFile[],autoProcess=false,threshold=.50)=>
    api<BatchUploadManifest>('/batches/'+encodeURIComponent(id)+'/upload-manifest',{
      method:'PUT',body:JSON.stringify({files,auto_process:autoProcess,grouping_threshold:threshold})
    }),
  cancelAutomatic:(id:string)=>post<{batch_id:string;auto_process_state:string}>(
    '/batches/'+encodeURIComponent(id)+'/auto-processing/cancel',{}),
  finishPending:(uploadId:string)=>api<{path:string;already_finalized?:boolean}>('/uploads/'+encodeURIComponent(uploadId)+'/finish',{method:'POST'}),
  cancelPending:(uploadId:string)=>del<{cancelled:boolean}>('/uploads/'+encodeURIComponent(uploadId)),
  create:(name:string,requestId:string,signal:AbortSignal)=>api<{batch_id:string;display_name:string}>('/batches',{
    method:'POST',signal,body:JSON.stringify({display_name:name,creation_request_id:requestId})
  }),
  rename:(id:string,name:string)=>patch<Batch>('/batches/'+id,{display_name:name}),
  gallery:(id:string,cursor?:string|null,limit=60)=>api<CursorPage<Photo>>('/batches/'+id+'/gallery'+query({cursor,limit})),
  removePhoto:(id:string,pid:string)=>del<{deleted:boolean}>('/batches/'+id+'/photos/'+pid),
  remove:(id:string)=>del<{state:string}>('/batches/'+id),
  deletion:(id:string)=>api<{batch_id:string;state?:'not_found';delete_state?:string;task?:{
    state:string;progress:DeletionProgress|null;error:string|null
  }|null}>('/batches/'+id+'/deletion'),
  thumbs:(id:string)=>api<{total:number;ready:number;failed:number}>('/thumbnails/status/'+id+'/counts'),
  retention:(id:string)=>api<Retention>('/batches/'+id+'/retention'),
  confirm:(id:string,runId:string)=>post<Retention>('/batches/'+id+'/downloads/confirm',{run_id:runId}),
  extend:(id:string)=>post<Retention>('/batches/'+id+'/retention/extend',{})
}
