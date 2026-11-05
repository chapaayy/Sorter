import type {ReferenceFile} from '../types/api'

/** Hash index of previously finalized reference photos, scoped by construction ID. */
export function indexReferenceHashes(files:readonly ReferenceFile[]):Map<string,Set<string>>{
  const index=new Map<string,Set<string>>()
  for(const file of files){
    if(!/^[0-9a-f]{64}$/i.test(file.sha256||''))continue
    let known=index.get(file.sam)
    if(!known){known=new Set();index.set(file.sam,known)}
    known.add(file.sha256.toLowerCase())
  }
  return index
}

/** Browser-local SHA-256. If unavailable, fall back to secure server deduplication. */
export async function fileSha256(file:File):Promise<string|null>{
  if(typeof crypto==='undefined'||!crypto.subtle)return null
  try{
    const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer())
    return Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('')
  }catch{return null}
}
