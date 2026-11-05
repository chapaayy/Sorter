import {api,post} from './client'
import type {StorageUsage,SystemStatus} from '../types/api'
export const systemApi={
  usage:()=>api<StorageUsage>('/storage/usage'),
  status:()=>api<SystemStatus>('/system/status'),
  cleanup:()=>post<{removed:number}>('/system/cache/cleanup',{})
}
