import {api,post} from './client'
import type {StorageUsage,SystemStatus,RetentionPreference} from '../types/api'
export const systemApi={
  usage:()=>api<StorageUsage>('/storage/usage'),
  status:()=>api<SystemStatus>('/system/status'),
  cleanup:()=>post<{removed:number}>('/system/cache/cleanup',{}),
  retention:()=>api<RetentionPreference>('/system/retention'),
  saveRetention:(value:RetentionPreference)=>api<RetentionPreference>('/system/retention',{
    method:'PATCH',body:JSON.stringify(value)
  })
}
