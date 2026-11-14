import type {CheckedReference,ReferenceReview} from '../types/referenceTransfer'

/** Compare exact content within a construction, regardless of filename. */
export function reviewReferences(files:readonly CheckedReference[],published:boolean[]):ReferenceReview{
  if(published.length!==files.length||published.some(match=>typeof match!=='boolean'))
    throw new Error('Сервер вернул неполный результат проверки образцов')
  const review:ReferenceReview={newFiles:[],duplicates:[],totalBytes:0}
  const seen=new Set<string>()
  for(const [index,file] of files.entries()){
    const key=JSON.stringify([file.sam,file.sha256,file.entry.file.size])
    if(published[index]||seen.has(key)){
      review.duplicates.push({...file,reason:published[index]?'library':'selection'})
    }else{
      review.newFiles.push(file)
      review.totalBytes+=file.entry.file.size
    }
    seen.add(key)
  }
  return review
}

/** Browser-local SHA-256, computed before sending any photo bytes. */
export async function fileSha256(file:File):Promise<string|null>{
  if(typeof crypto==='undefined'||!crypto.subtle)return null
  try{
    const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer())
    return Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('')
  }catch{return null}
}
