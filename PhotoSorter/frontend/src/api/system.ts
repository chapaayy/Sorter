import {api,post} from './client'
import type {StorageUsage,SystemStatus,RetentionPreference,StorageInventorySummary,StorageInventoryPage,HostAuditReport,LiveAuditStatus,MapUpdateStatus,StorageAccountsPage,StorageAccountDetail,StorageOperations,StorageIssues,StorageMaintenance,StoragePreview,MaintenanceKind,HostMaintenanceKind} from '../types/api'
export const systemApi={
  updateStatus:()=>api<MapUpdateStatus>('/system/update'),
  checkUpdate:()=>post<MapUpdateStatus>('/system/update/check',{}),
  startUpdate:()=>post<MapUpdateStatus>('/system/update/start',{}),
  usage:()=>api<StorageUsage>('/storage/usage'),
  storageAccounts:(offset=0)=>api<StorageAccountsPage>('/storage/accounts?offset='+offset),
  storageAccount:(id:string,offset=0)=>api<StorageAccountDetail>('/storage/accounts/'+encodeURIComponent(id)+'?offset='+offset),
  storageOperations:()=>api<StorageOperations>('/storage/operations'),
  storageIssues:(offset=0)=>api<StorageIssues>('/storage/accounting/issues?limit=50&offset='+offset),
  reconcile:()=>post<{requested_at:string}>('/storage/reconcile',{}),
  maintenance:()=>api<StorageMaintenance[]>('/storage/maintenance'),
  maintenancePreview:(kind:MaintenanceKind)=>api<StoragePreview>('/storage/maintenance/'+kind+'/preview'),
  maintenanceStart:(kind:MaintenanceKind)=>post<StorageMaintenance>('/storage/maintenance/'+kind,{confirmed:true}),
  hostMaintenancePreview:(kind:HostMaintenanceKind)=>api<StoragePreview>('/storage/host-maintenance/'+kind+'/preview'),
  hostMaintenanceStart:(kind:HostMaintenanceKind)=>post<MapUpdateStatus>('/storage/host-maintenance/'+kind,{confirmed:true}),
  scanInventory:()=>post<StorageInventorySummary>('/storage/inventory/scan',{}),
  inventoryFiles:(snapshotId:string,offset=0,category='',search='')=>
    api<StorageInventoryPage>('/storage/inventory/files?'+new URLSearchParams({
      snapshot_id:snapshotId,offset:String(offset),limit:'100',category,search
    }).toString()),
  hostAudit:()=>api<HostAuditReport>('/storage/host-audit'),
  liveAudit:()=>api<LiveAuditStatus>('/storage/host-audit/live'),
  status:()=>api<SystemStatus>('/system/status'),
  retention:()=>api<RetentionPreference>('/system/retention'),
  saveRetention:(value:RetentionPreference)=>api<RetentionPreference>('/system/retention',{
    method:'PATCH',body:JSON.stringify(value)
  })
}
