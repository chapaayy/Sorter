import {defineStore} from 'pinia'
import {ref,watch} from 'vue'

export const DEFAULT_PARALLEL_UPLOADS=5
export const MAX_PARALLEL_UPLOADS=10
const STORAGE_KEY='ps.upload.parallel'

export function normalizeParallelUploads(value:unknown):number{
  const number=Number(value)
  return Number.isInteger(number)&&number>=1&&number<=MAX_PARALLEL_UPLOADS
    ? number : DEFAULT_PARALLEL_UPLOADS
}

export const useUploadSettingsStore=defineStore('upload-settings',()=>{
  let stored:unknown=DEFAULT_PARALLEL_UPLOADS
  try{stored=localStorage.getItem(STORAGE_KEY)??DEFAULT_PARALLEL_UPLOADS}
  catch{ /* local storage may be unavailable */ }
  const parallelUploads=ref(normalizeParallelUploads(stored))
  watch(parallelUploads,value=>{
    const valid=normalizeParallelUploads(value)
    if(valid!==value){parallelUploads.value=valid;return}
    try{localStorage.setItem(STORAGE_KEY,String(valid))}catch{}
  },{immediate:true})
  return {parallelUploads}
})
