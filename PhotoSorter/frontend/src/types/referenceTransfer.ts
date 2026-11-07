import type {UploadEntry} from '../utils/upload'

/** A single reference file with its validated construction name and address. */
export interface ReferenceTransferItem {
  sam:string
  address?:string
  entry:UploadEntry
}
