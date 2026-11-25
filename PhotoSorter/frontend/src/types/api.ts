export type ThemeChoice = 'system' | 'dark' | 'light'
export interface User { username: string }
export interface DeletionProgress {
  phase:'queued'|'stopping_jobs'|'waiting_operations'|'scanning'|'files'|'database'|'completed'
  done:number
  total:number|null
}
export interface MediaProfile {image_format:'jpg'|'png';video_format:'mp4'|'webm'}
export interface MediaPreparation {
  state:'queued'|'running'|'interrupted'|'completed'|'completed_with_errors'|'failed'|'stopped'
  total_count:number;completed_count:number;failed_count:number;error?:string|null
  progress_percent?:number|null;eta_seconds?:number|null;current_file?:string|null
}
export interface Batch {
  batch_id: string; display_name: string; created_at: string; report_date_mode?:'manual'|'processing';report_date?:string|null; upload_state: string
  thumbnail_state: string; delete_state: string; deleted_at?: string | null
  deletion_progress?:DeletionProgress|null
  download_confirmed_at?: string | null; confirmed_run_id?: string | null
  delete_after_at?: string | null; photos?: number; videos?:number; media_files?: number; size_bytes?: number; runs?: number; pending?: number
  upload_manifest_state?: 'waiting'|'complete'|null;upload_manifest_completed_at?: string|null
  auto_process_regions?:string[]|null
  auto_process_state?: 'waiting'|'queued'|'cancelled'|'manual'|null
  auto_process_run_id?: string|null; auto_process_error?: string|null
  auto_process_threshold?: number
  media_image_format?:MediaProfile["image_format"]|null; media_preparation?:MediaPreparation|null
  latest_run?:Run|null;last_result_run_id?:string|null;cover_thumbnail_url?:string|null
}
export interface UploadManifestFile {upload_id:string;relative_path:string;filename:string;size:number}
export interface RetentionPreference {
  enabled:boolean;value:number;unit:'minutes'|'hours'|'days'|'months'
}
export interface WorkloadSettings {
  mode:'auto'|'manual';fo_threads:number;reference_threads:number;max_threads:number
  total_cpus:number;model_cpus:number;system_cpus:number;max_model_cpus:number
  background_policy:string;model_limit_applies:string
  zip_mode:string;docker_limits_editable:boolean;applies:string
}
export interface CpuSettings {threads:number;max_threads:number;applies:string;docker_quota_changes:boolean}
export interface ProcessingSettings {
  model:'megaloc';auto_process_new_batches:boolean;grouping_threshold:number;min_match_score:number
}
export interface BatchUploadManifest {
  state:'legacy'|'waiting'|'complete';completed_at?:string|null
  auto_process_regions?:string[]|null
  auto_process_state?: 'waiting'|'queued'|'cancelled'|'manual'|null
  auto_process_run_id?:string|null;auto_process_error?:string|null;auto_process_threshold?:number
  expected:number;finalized:number;missing:number;pending:number
  files:Array<UploadManifestFile & {state:'not_started'|'unfinished'|'finalized'|'missing_saved';received:number}>
}
export interface PendingUpload {
  id:string;filename:string;size:number;received:number;updated_at:string
  has_part:boolean;can_finalize:boolean;prefix_bytes:number;prefix_sha256:string|null
}
export interface PendingUploadList { uploads:PendingUpload[];total:number }
export interface Photo {
  id: string; name: string; bytes: number; created_at: string; side?:string|null
  original_media_type?: string | null
  media_kind?:"video"|"image"|null; play_url?:string|null; preview_url?:string|null; media_error?:string|null;duration?:number|null
  thumbnail_status?: 'queued' | 'running' | 'pending' | 'ready' | 'failed'
  thumbnail_url?: string | null; original_url?: string | null
}
export interface CursorPage<T> { photos: T[]; next_cursor: string | null }
export interface SamCount { sam: string; kind?:'standard'|'custom'; photos: number; address?: string | null; city_code?: string | null; construction_number?: string | null; display_name?: string }
export interface ReferenceFile { id: string; sam: string; name: string; sha256: string }
export interface RunProgress {
  model?: string | null; stage?: string; stage_label?: string; detail?: string
  current?: number; total?: number; stage_percent?: number | null
  elapsed_seconds?: number; stage_items_per_second?: number
  estimated_remaining_seconds?: number | null; overall_percent?: number | null; eta_status?: string
}
export interface Run {
  id: string; batch_id: string; status: string; selected_regions?:string[]|null; created_at?: string
  started_at?: string
  actual_started_at?: string; finished_at?: string; actual_finished_at?: string
  grouping_threshold?: number; min_match_score?:number;selected_models?: string[];source?:'manual'|'automatic'
  queue_position?: number | null; models?: Record<string, { status?: string; count?: number; processed?:number; assigned?:number; uncertain?:number; groups?: number }>
  progress?: RunProgress; error?: string; archive_state?:'preparing'|'ready'|'failed'|'on_demand'
}
export interface ResultPhoto {
  index: number; assigned_sam?: string; group_id?: string;side?:string|null
  score?: number | null; verdict?: string; reason?: string
  media_kind?:"video"|"image"|null; filename?:string|null;duration?:number|null
  thumbnail_url?: string | null; image_url: string
}
export interface Retention {
  batch_id: string; delete_state: string; download_confirmed_at?: string | null
  delete_after_at?: string | null; confirmed_run_id?: string | null
  warning?: boolean; stale_unconfirmed?: boolean
}
export interface LogEntry { at: string; level: string; model?: string | null; source?: string; message: string }
export interface ModelInfo {
  models: Array<{ id: string; title: string; available: boolean; reason?: string; downloadable: boolean }>
  device: string; downloads?: Record<string, unknown>
}
export interface StoragePolicy {personal_enabled:boolean;temporary_limit_bytes:number|null;disk_reserve_bytes:number|null}
export interface StorageBudget {used_bytes:number;reserved_bytes:number;limit_bytes:number|null;enabled:boolean;available_bytes:number|null;state:'unlimited'|'ok'|'warning'|'full'|'exceeded'}
export interface StorageLimits {
  policy:StoragePolicy;registry_ready:boolean;total_bytes:number
  disk:{used_bytes:number;free_bytes:number;reserved_bytes:number;minimum_bytes:number;baseline_bytes:number;available_bytes:number}
  temporary:StorageBudget
}
export interface StorageCounter {
  allocated_bytes:number;logical_bytes:number;files:number;hardlink_paths:number
  hardlink_reused_bytes?:number;charged_bytes?:number
}
export interface StorageCapacity {
  total_bytes:number;used_bytes:number;available_bytes:number
  map_allocated_bytes?:number|null;outside_map_or_unexplained_bytes?:number|null
}
export interface StorageHistory {
  objects:number;object_bytes:number;embeddings:number;embedding_bytes:number;missing:number;partial:boolean
}
export interface StorageRegistry {
  sampled_at:string|null;reconciled_at:string|null;started_at:string|null;requested_at?:string|null
  partial:boolean;stale:boolean;reconciling:boolean;reconciliation_requested?:boolean;pending_changes:number;errors:number
  allocated_bytes?:number;logical_bytes?:number;categories?:Record<string,StorageCounter>
  owners?:Record<string,StorageCounter>;devices?:Record<string,StorageCounter>
  temporary?:StorageCounter;temporary_peak_bytes:number;reference_history?:StorageHistory
  missing_expected?:number;issues?:Record<string,number>;cross_owner_inode_conflicts?:number
  reserved_bytes?:number;reservations?:Record<string,{bytes:number;operations:number}>;temporary_budget?:StorageBudget
  unfinished_fo?:{files:number;remaining_bytes:number};unfinished_references?:{files:number;remaining_bytes:number}
  temporary_operations?:{rows:Array<{operation_key:string;category:string;owner_id:number|null;batch_id:string|null;run_id:string|null;files:number;logical_bytes:number;allocated_bytes:number}>;total_groups:number;partial:boolean}
}
export interface PhysicalTreeBucket {file_bytes:number;directory_bytes:number;files:number;directories:number;hardlink_paths:number}
export interface PhysicalTreeSample {
  finished_at:string;started_at?:string;device?:string;allocated_bytes?:number;directory_bytes?:number
  partial:boolean;comparable:boolean;errors:number;entries?:number;changed_directories?:number
  limit_reached?:boolean;cross_scope_links?:number;other_devices?:number;excluded_mounts?:number
  registry_file_bytes?:number|null;host_file_bytes?:number|null;app_delta_bytes?:number|null;host_delta_bytes?:number|null
  unexplained_bytes?:number|null;absolute_discrepancy_bytes?:number|null;unknown_bytes?:number|null;unknown_files?:number|null
}
export type RootDiskSample=PhysicalTreeSample & {
  filesystem?:string|null;scopes?:string[];paths?:Record<string,string>
  map_storage?:PhysicalTreeBucket;docker_engine?:PhysicalTreeBucket;containerd_default?:PhysicalTreeBucket
  system_logs?:PhysicalTreeBucket;other_visible?:PhysicalTreeBucket
  residual_bytes?:number|null;capacity_before?:StorageCapacity;capacity_after?:StorageCapacity
  mount_table_changed?:boolean;deleted_open?:{allocated_bytes:number;files:number;partial:boolean;errors:number;limit_reached:boolean}
}
export interface StorageCheckHistoryRow {
  finished_at:string;allocated_bytes?:number|null;directory_bytes?:number|null;comparable:boolean
  unexplained_bytes?:number|null;absolute_discrepancy_bytes?:number|null;unknown_bytes?:number|null;unknown_files?:number|null
  residual_bytes?:number|null;device?:string|null
}
export interface StorageHost {
  at:string;partial:boolean;stale:boolean;errors:number;engine_sampled_at?:string
  categories:Record<string,StorageCounter>;devices:Record<string,StorageCounter>
  unknown_sample?:Array<{path:string;reason:string;logical_bytes:number}>
  tree_check?:PhysicalTreeSample;disk_check?:RootDiskSample
  tree_history?:StorageCheckHistoryRow[];disk_history?:StorageCheckHistoryRow[]
  postgres_wal_subset_bytes?:number;postgres_wal_delta_bytes?:number|null
  docker?:{available:boolean;shared_engine_totals:Array<{Type?:string;Size?:string;Reclaimable?:string;TotalCount?:string|number;Active?:string|number}>;map_revision_images:Array<{ID:string;Tag:string;Size:string}>;limitations:string[]}
  tmpfs?:{available:boolean;partial:boolean;devices:Record<string,StorageCapacity>;mounts:Array<{service:string;mount:string;device:string}>}|null
  deleted_open?:{allocated_bytes:number;logical_bytes:number;files:number;partial:boolean}|null
}
export interface StorageUsage {
  disk:StorageCapacity & {device?:number;used_fraction:number;reserved_bytes?:number;operation_reserved_bytes?:number;allocatable_bytes?:number;warning?:'warning'|'critical'|null}
  filesystems?:Record<string,StorageCapacity>;categories_bytes:Record<string,number>
  registry?:StorageRegistry;host?:StorageHost|null;database_estimated_bytes?:number|null
  postgres_diagnostics?:{open_transactions:number;long_transactions:number;oldest_transaction_seconds:number;estimated_dead_tuples:number;autovacuum_count:number;last_autovacuum:string|null}|null
  journals?:{at:string|null;services:Record<string,{bytes:number|null;budget_bytes:number;partial:boolean}>}
}
export interface StorageAccount {id:string;username:string;access_role:string;usage?:StorageCounter|null;quota?:StorageBudget}
export interface StorageAccountsPage {rows:StorageAccount[];total:number;offset:number;limit:number;sampled_at:string|null;partial:boolean}
export interface StorageAccountDetail {
  account:StorageAccount;categories:Record<string,StorageCounter>;batches:Array<{batch_id:string;display_name:string;categories:Record<string,StorageCounter>}>
  total:number;offset:number;limit:number;sampled_at:string|null;basis:string
}
export interface StorageOperations {
  io_leases?:Array<{kind:string;operations:number;last_seen:string}>
  active_queue:Array<{seq:number;kind:string;state:string;fo_run_id:string|null;batch_id:string|null;display_name:string|null;started_at:string|null}>
  archives:Array<{category:string;files:number;expired:number;next_eligible_at:string}>
  unfinished_fo_next_eligible_at:string|null;unfinished_reference_next_eligible_at?:string|null;archive_ttl_seconds:number;scratch_grace_seconds:number
  cleanup_worker:{alive:boolean;last_seen:string|null}
}
export interface StorageIssues {files:Array<{path:string;category:string;issue:string;logical_bytes:number;allocated_bytes:number}>;missing:Array<{path:string;issue:string}>;offset:number;limit:number;snapshot:string|null}
export type MaintenanceKind='expired_archives'|'unused_thumbnails'|'abandoned_scratch'
export type HostMaintenanceKind='storage-cache'|'storage-logs'
export interface HostStorageAction {kind:HostMaintenanceKind;state:'running'|'completed'|'failed'|'interrupted';started_at?:string|null;finished_at?:string|null;removed?:number|null;available_delta_bytes?:number|null;detail?:string}
export interface StorageMaintenance {kind:MaintenanceKind;state:'queued'|'running'|'completed'|'failed'|'interrupted';requested_at:string;started_at:string|null;finished_at:string|null;removed:number|null;detail:string|null;available_delta_bytes?:number|null}
export interface StoragePreview {kind:MaintenanceKind|HostMaintenanceKind;files:number|null;allocated_bytes:number|null;logical_excess_bytes?:number|null;sampled_at:string|null;partial:boolean;basis:string}
export interface SystemStatus {
  at: string; worker: { queue: Record<string, number>; expected_threads: number }
  thumbnails: Record<string, number>;
  services?: Record<string, { alive: boolean; last_seen: string | null }>;
  disk: { total_bytes: number; available_bytes: number; reserved_bytes: number }
  api: { uptime_seconds: number; latency: { samples: number; p50_ms: number | null; p95_ms: number | null }; rss_peak_kib: number }
}

export interface InventoryStats {
  files:number;logical_bytes:number;allocated_bytes:number;hardlink_paths:number
}
export interface StorageInventorySummary {
  snapshot_id:string;captured_at:string;files_scanned:number
  allocated_bytes:number;logical_bytes:number
  categories:Record<string,InventoryStats>;skipped_paths:number;partial:boolean
  scan_seconds:number;checked_roots:string[];not_scanned:string[]
  batch_metadata_available:boolean;description:string
}
export interface StorageInventoryFile {
  path:string;category:string;purpose:'permanent'|'temporary'|'cache'|'system'|'service'|'archive'|'unknown'
  owner_kind:string;owner_id:string|null;owner_name:string|null
  logical_bytes:number;allocated_bytes:number;hardlink:boolean;links:number;modified_at:string
  issue?:string|null;registry_category?:string
}
export interface StorageInventoryPage {
  snapshot_id:string;total:number;offset:number;limit:number;files:StorageInventoryFile[]
}

export interface HostAuditCounter {
  files:number;allocated_bytes:number;logical_bytes:number;hardlink_paths?:number
}
export interface HostAuditReport {
  available:boolean;csv_available?:boolean;write_sites_available?:boolean;write_sites_count?:number;detail?:string
  snapshot_id?:string;captured_at?:string;files_scanned?:number
  allocated_bytes?:number;skipped_paths?:number;scan_seconds?:number;container_root_mounts_excluded?:number
  scopes?:Record<string,HostAuditCounter>
  categories?:Record<string,HostAuditCounter>
  docker?:{
    containers:number;volumes:number;driver:string|null
    matched_image_layers:number;global_shared_disk_usage:unknown[]
  }
  errors?:string[];limitations?:string[]
  containerd_attribution?:{
    driver?:string;matched_snapshots?:number;container_mount_references?:number
    image_chains_checked?:number;image_chains_matched?:number|null
    ctr_snapshot_metadata_checked?:boolean;snapshot_keys_listed?:number
    categories?:Record<string,HostAuditCounter>;snapshot_owners?:Record<string,{
      category:string;owners:string[];roles:string[];sources:string[]
    }>;warnings?:string[];limitations?:string[]
  }
}

export interface LiveAuditStatus {
  available:boolean;download_available?:boolean;detail?:string
  schema?:string;running?:boolean;started_at?:string
  heartbeat_at?:string;last_event_at?:string;events?:number
  postgres_shm_close_writes_aggregated?:number
  postgres_shm_pending?:number;events_observed_including_aggregates?:number
  events_by_type?:Record<string,number>;queue_overflows?:number
  watch_errors?:number;watched_directories?:number
  watched_roots?:Array<{path:string;scope:string}>
  warnings?:string[];limitations?:string[]
}

export interface MapUpdateStatus {
  storage_maintenance_supported?:boolean;storage_action?:HostStorageAction
  branch?:string
  available:boolean;busy?:boolean;phase?:string;detail?:string
  installed?:string|null;target?:string|null;previous?:string|null;update_available?:boolean
  free_before?:number;free_after?:number;free_change?:number;warnings?:string[]
}
