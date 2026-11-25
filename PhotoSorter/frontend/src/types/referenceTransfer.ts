import type {UploadEntry} from '../utils/upload'

/** A single reference file with its validated construction name and address. */
export interface ReferenceTransferItem {
  sam:string
  address?:string
  side?:string|null
  entry:UploadEntry
}

export interface CheckedReference extends ReferenceTransferItem {
  sha256:string
}
export interface DuplicateReference extends CheckedReference {
  reason:'library'|'selection'
}
export interface ReferenceReview {
  newFiles:CheckedReference[]
  duplicates:DuplicateReference[]
  totalBytes:number
}
