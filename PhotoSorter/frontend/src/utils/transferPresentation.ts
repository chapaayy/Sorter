import type {UploadProgress,UploadRow,UploadStatus} from '../types/uploadQueue'

const LABELS:Record<UploadStatus,string>={
  waiting:'Ждёт очереди',running:'Загружается',pausing:'Приостанавливается',
  paused:'Приостановлено',failed:'Ошибка загрузки',cancelling:'Отменяется'
}
export const uploadStatusLabel=(status:UploadStatus)=>LABELS[status]
export const uploadKindLabel=(kind:UploadRow['kind'])=>kind==='fo'?'ФО':'Образцы'
export function uploadPercent(progress:UploadProgress){
  return progress.totalBytes>0?Math.max(0,Math.min(100,Math.floor(progress.sentBytes/progress.totalBytes*100))):0
}
