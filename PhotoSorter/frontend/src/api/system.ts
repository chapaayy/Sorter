import {api,post} from './client'
import type {StorageUsage,StorageBreakdown,SystemStatus,RetentionPreference,StorageInventorySummary,StorageInventoryPage,HostAuditReport,LiveAuditStatus,MapUpdateStatus} from '../types/api'
export const systemApi={
  updateStatus:()=>api<MapUpdateStatus>('/system/update'),
  checkUpdate:()=>post<MapUpdateStatus>('/system/update/check',{}),
  startUpdate:()=>post<MapUpdateStatus>('/system/update/start',{}),
  usage:()=>api<StorageUsage>('/storage/usage'),
  breakdown:()=>api<StorageBreakdown>('/storage/breakdown'),
  scanInventory:()=>post<StorageInventorySummary>('/storage/inventory/scan',{}),
  inventoryFiles:(snapshotId:string,offset=0,category='',search='')=>
    api<StorageInventoryPage>('/storage/inventory/files?'+new URLSearchParams({
      snapshot_id:snapshotId,offset:String(offset),limit:'100',category,search
    }).toString()),
  hostAudit:()=>api<HostAuditReport>('/storage/host-audit'),
  liveAudit:()=>api<LiveAuditStatus>('/storage/host-audit/live'),
  status:()=>api<SystemStatus>('/system/status'),
  cleanup:()=>post<{removed:number}>('/system/cache/cleanup',{}),
  retention:()=>api<RetentionPreference>('/system/retention'),
  saveRetention:(value:RetentionPreference)=>api<RetentionPreference>('/system/retention',{
    method:'PATCH',body:JSON.stringify(value)
  })
}
