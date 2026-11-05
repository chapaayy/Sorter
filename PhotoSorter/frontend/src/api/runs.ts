import {api,post,query} from './client'
import type {Run,ModelInfo} from '../types/api'
export const runApi={
  list:(limit=100,offset=0)=>api<{runs:Run[];total:number}>('/runs'+query({limit,offset})),
  one:(id:string)=>api<Run>('/runs/'+encodeURIComponent(id)),
  start:(id:string,threshold:number)=>post<Run>('/runs',{batch_id:id,grouping_threshold:threshold}),
  stop:(id:string)=>post<Run>('/runs/'+id+'/stop',{}),
  models:()=>api<ModelInfo>('/models'),
  downloadModel:()=>post<unknown>('/models/megaloc/download',{})
}
