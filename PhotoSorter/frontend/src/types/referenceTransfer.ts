import type {UploadEntry} from '../utils/upload'

/** A single reference file with its validated construction name and address. */
export interface ReferenceTransferItem {
  sam:string
  address?:string
  side?:string|null
  portable?:boolean
  expectedSha256?:string
  entry:UploadEntry
}

export interface CheckedReference extends ReferenceTransferItem {
  sha256:string
}
export interface DuplicateReference extends CheckedReference {
  reason:'library'|'selection'
}
export interface ReferenceSideConflict{
  reference_id:string
  existing_side:string|null
  requested_side:string
  file:CheckedReference
}
export interface ReferenceReview {
  newFiles:CheckedReference[]
  duplicates:DuplicateReference[]
  totalBytes:number
  sideConflicts?:ReferenceSideConflict[]
}
