export type ThemeChoice = 'system' | 'dark' | 'light'
export interface User { username: string }
export interface Batch {
  batch_id: string; display_name: string; created_at: string; upload_state: string
  thumbnail_state: string; delete_state: string; deleted_at?: string | null
  download_confirmed_at?: string | null; confirmed_run_id?: string | null
  delete_after_at?: string | null; photos?: number; size_bytes?: number; runs?: number; pending?: number
  upload_manifest_state?: 'waiting'|'complete'|null;upload_manifest_completed_at?: string|null
  auto_process_state?: 'waiting'|'queued'|'cancelled'|'manual'|null
  auto_process_run_id?: string|null; auto_process_error?: string|null
  auto_process_threshold?: number
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
  model:'megaloc';auto_process_new_batches:boolean;grouping_threshold:number
}
export interface BatchUploadManifest {
  state:'legacy'|'waiting'|'complete';completed_at?:string|null
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
  id: string; name: string; bytes: number; created_at: string
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
  id: string; batch_id: string; status: string; created_at?: string
  started_at?: string
  actual_started_at?: string; finished_at?: string; actual_finished_at?: string
  grouping_threshold?: number; selected_models?: string[];source?:'manual'|'automatic'
  queue_position?: number | null; models?: Record<string, { status?: string; count?: number; processed?:number; assigned?:number; uncertain?:number; groups?: number }>
  progress?: RunProgress; error?: string; archive_state?:'preparing'|'ready'|'failed'
}
export interface ResultPhoto {
  index: number; assigned_sam?: string; group_id?: string
  score?: number | null; verdict?: string; reason?: string
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
export interface StorageUsage {
  disk: { total_bytes: number; used_bytes: number; available_bytes: number; used_fraction: number
    warning?: 'warning' | 'critical' | null; reserved_bytes?: number; admission_ok?: boolean }
  categories_bytes: Record<string, number>; database_estimated_bytes?: number | null; not_scanned?: string[]
}
export interface SystemStatus {
  at: string; worker: { queue: Record<string, number>; expected_threads: number }
  thumbnails: Record<string, number>;
  services?: Record<string, { alive: boolean; last_seen: string | null }>;
  disk: { total_bytes: number; available_bytes: number; reserved_bytes: number }
  api: { uptime_seconds: number; latency: { samples: number; p50_ms: number | null; p95_ms: number | null }; rss_peak_kib: number }
}
