import {api,post,query} from './client'
import type {QueueTask,PreparationDetail,LayoutPreparationDetail} from '../types/workQueue'

export const workQueueApi={
  list:(scope:'active'|'history'|'all'='active',limit=100,offset=0)=>
    api<{tasks:QueueTask[];total:number}>('/work-queue'+query({scope,limit,offset})),
  preparation:(jobId:string)=>api<PreparationDetail>('/reference-preparations/'+jobId),
  retry:(jobId:string,idempotency_key:string)=>
    post<{state:string;already_applied:boolean}>('/reference-preparations/'+jobId+'/retry',{idempotency_key}),
  skip:(jobId:string,idempotency_key:string)=>
    post<{state:string;already_applied:boolean}>('/reference-preparations/'+jobId+'/skip',{idempotency_key}),
  stop:(jobId:string)=>post<{state:string;stop_requested:boolean}>(
    '/reference-preparations/'+jobId+'/stop',{}),
  layoutPreparation:(id:string)=>api<LayoutPreparationDetail>('/layout-preparations/'+id),
  retryLayout:(id:string)=>post<{state:string}>('/layout-preparations/'+id+'/retry',{}),
  skipLayout:(id:string)=>post<{state:string}>('/layout-preparations/'+id+'/skip',{})
}
