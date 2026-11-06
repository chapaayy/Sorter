import {api,post,query} from './client'
import type {Run,ModelInfo,ProcessingSettings} from '../types/api'
export const runApi={
  list:(limit=100,offset=0)=>api<{runs:Run[];total:number}>('/runs'+query({limit,offset})),
  one:(id:string)=>api<Run>('/runs/'+encodeURIComponent(id)),
  start:(id:string,threshold:number)=>post<Run>('/runs',{batch_id:id,grouping_threshold:threshold}),
  stop:(id:string)=>post<Run>('/runs/'+id+'/stop',{}),
  models:()=>api<ModelInfo>('/models'),
  autoSettings:()=>api<ProcessingSettings>('/processing-settings'),
  saveAutoSettings:(enabled:boolean,threshold:number)=>api<ProcessingSettings>(
    '/processing-settings',{method:'PATCH',body:JSON.stringify({
      auto_process_new_batches:enabled,grouping_threshold:threshold
    })}),
  downloadModel:()=>post<unknown>('/models/megaloc/download',{})
}
