import type {PendingUpload} from './api'
import type {ReferenceReview} from './referenceTransfer'
import type {UploadEntry} from '../utils/upload'

export type RecoverySource={batchId:string;item:PendingUpload;file:File}
export type UploadSource=
  |{kind:'fo';name:string;entries:readonly UploadEntry[];autoProcess:boolean;threshold:number}
  |{kind:'recovery';source:RecoverySource}
  |{kind:'references';name:string;review:ReferenceReview;success:string}
export type UploadCompletion={batchId:string}|{sam?:string}
export type UploadResult={message:string;completion?:UploadCompletion;action?:{to:string;label:string}}
export type UploadProgress={
  phase:string;sentBytes:number;totalBytes:number;completed:number;totalFiles:number;duplicates?:number
}
export type UploadContext={
  signal:AbortSignal;parallel:number;report:(progress:UploadProgress)=>void;setBatch:(id:string)=>void
}
export type UploadStatus='waiting'|'running'|'pausing'|'paused'|'failed'|'cancelling'
export interface UploadRow extends UploadProgress{
  id:number;name:string;kind:'fo'|'references';status:UploadStatus;error:string;batchId?:string
}
