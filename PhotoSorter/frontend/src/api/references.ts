import {api,del,patch,query} from './client'
import type {CursorPage,Photo,SamCount,ReferenceFile} from '../types/api'
export const referenceApi={
  list:()=>api<{sam:SamCount[];total:number}>('/references'),
  gallery:(sam:string,cursor?:string|null,limit=60)=>api<CursorPage<Photo>>('/references/'+encodeURIComponent(sam)+'/photos'+query({cursor,limit})),
  files:()=>api<{files:ReferenceFile[]}>('/references/files'),
  remove:(id:string)=>del<{deleted:boolean}>('/references/files/'+id),
  renameSam:(sam:string,name:string)=>patch<{sam:string}>('/references/sam/'+encodeURIComponent(sam),{new_sam:name}),
  deleteSam:(sam:string)=>del<{deleted:boolean}>('/references/sam/'+encodeURIComponent(sam)),
  cache:()=>api<{total:number;cached:number;current_signature?:string|null}>('/references/cache/status')
}
