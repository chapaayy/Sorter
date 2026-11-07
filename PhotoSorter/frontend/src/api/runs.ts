import {api,post,query} from './client'
import type {Run,ModelInfo,ProcessingSettings,CpuSettings,WorkloadSettings} from '../types/api'
export const runApi={
  list:(limit=100,offset=0)=>api<{runs:Run[];total:number}>('/runs'+query({limit,offset})),
  active:()=>api<{runs:Run[];total:number}>('/runs'+query({scope:'active',limit:25})),
  history:(limit=30,offset=0)=>api<{runs:Run[];total:number}>(
    '/runs'+query({scope:'history',limit,offset})),
  one:(id:string)=>api<Run>('/runs/'+encodeURIComponent(id)),
  start:(id:string,threshold:number)=>post<Run>('/runs',{batch_id:id,grouping_threshold:threshold}),
  stop:(id:string)=>post<Run>('/runs/'+id+'/stop',{}),
  retryArchive:(id:string)=>post<{run_id:string;state:string}>('/runs/'+encodeURIComponent(id)+'/archive/retry',{}),
  models:()=>api<ModelInfo>('/models'),
  autoSettings:()=>api<ProcessingSettings>('/processing-settings'),
  saveAutoSettings:(enabled:boolean,threshold:number)=>api<ProcessingSettings>(
    '/processing-settings',{method:'PATCH',body:JSON.stringify({
      auto_process_new_batches:enabled,grouping_threshold:threshold
    })}),
  cpuSettings:()=>api<CpuSettings>('/processing-settings/cpu'),
  saveCpuThreads:(threads:number)=>api<CpuSettings>(
    '/processing-settings/cpu',{method:'PATCH',body:JSON.stringify({threads})}),
  workloadSettings:()=>api<WorkloadSettings>('/processing-settings/workloads'),
  saveWorkloadSettings:(mode:'auto'|'manual',fo_threads:number,reference_threads:number)=>
    api<WorkloadSettings>('/processing-settings/workloads',{
      method:'PATCH',body:JSON.stringify({mode,fo_threads,reference_threads})
    }),
  downloadModel:()=>post<unknown>('/models/megaloc/download',{})
}
