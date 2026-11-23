import {api,post} from './client'
import type {StorageUsage,StorageBreakdown,SystemStatus,RetentionPreference} from '../types/api'
export const systemApi={
  usage:()=>api<StorageUsage>('/storage/usage'),
  breakdown:()=>api<StorageBreakdown>('/storage/breakdown'),
  status:()=>api<SystemStatus>('/system/status'),
  cleanup:()=>post<{removed:number}>('/system/cache/cleanup',{}),
  retention:()=>api<RetentionPreference>('/system/retention'),
  saveRetention:(value:RetentionPreference)=>api<RetentionPreference>('/system/retention',{
    method:'PATCH',body:JSON.stringify(value)
  })
}
