import {api,del,patch,post,query} from './client'
import type {CursorPage,Photo,SamCount,ReferenceFile} from '../types/api'
export interface ImportPlanEntry{
  sam:string;name:string;address:string;city_code:string;number:string;existing:boolean;photos:number
}
export interface ImportPlanError{folder:string;reason:string}
export interface ImportPlan{entries:ImportPlanEntry[];errors:ImportPlanError[];cities:Record<string,string>}
export type NewConstruction =
  |{kind:'standard';city_code:string;number:string;address:string}
  |{kind:'custom';name:string}
export interface CreatedConstruction{sam:string;display_name:string;kind:'standard'|'custom';photos:number}
export const referenceApi={
  createConstruction:(value:NewConstruction)=>post<CreatedConstruction>('/references/constructions',value),
  importPreview:(folders:string[])=>post<ImportPlan>('/references/import/preview',{folders}),
  changeAddress:(sam:string,address:string)=>patch<{sam:string;address:string;name:string}>(
    '/references/constructions/'+encodeURIComponent(sam)+'/address',{address}),
  list:()=>api<{sam:SamCount[];total:number}>('/references'),
  gallery:(sam:string,cursor?:string|null,limit=60)=>api<CursorPage<Photo>>('/references/'+encodeURIComponent(sam)+'/photos'+query({cursor,limit})),
  files:()=>api<{files:ReferenceFile[]}>('/references/files'),
  remove:(id:string)=>del<{deleted:boolean}>('/references/files/'+id),
  renameSam:(sam:string,name:string)=>patch<{sam:string}>('/references/sam/'+encodeURIComponent(sam),{new_sam:name}),
  deleteSam:(sam:string)=>del<{deleted:boolean}>('/references/sam/'+encodeURIComponent(sam)),
  cache:()=>api<{total:number;cached:number;current_signature?:string|null}>('/references/cache/status')
}
