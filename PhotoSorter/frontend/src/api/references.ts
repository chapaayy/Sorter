import {api,del,patch,post,query} from './client'
import type {CursorPage,Photo,SamCount,ReferenceFile} from '../types/api'
export interface ImportPlanEntry{
  sam:string;name:string;address:string;city_code:string;number:string;existing:boolean;photos:number
}
export interface ImportPlanError{folder:string;reason:string}
export interface ImportPlan{entries:ImportPlanEntry[];errors:ImportPlanError[];new_regions:string[]}
export type NewConstruction =
  |{kind:'standard';city_code:string;number:string;address:string}
  |{kind:'custom';name:string}
export interface CreatedConstruction{sam:string;display_name:string;kind:'standard'|'custom';photos:number}
export interface UpdatedConstruction{sam:string;previous_sam:string;display_name:string;kind:'standard'|'custom';changed:boolean;version?:number;city_code?:string|null;construction_number?:string|null;address?:string|null}
export const referenceApi={
  createConstruction:(value:NewConstruction)=>post<CreatedConstruction>('/references/constructions',value),
  updateConstruction:(sam:string,value:NewConstruction)=>patch<UpdatedConstruction>(
    '/references/constructions/'+encodeURIComponent(sam),value),
  importPreview:(folders:string[])=>post<ImportPlan>('/references/import/preview',{folders}),
  changeAddress:(sam:string,address:string)=>patch<{sam:string;address:string;name:string}>(
    '/references/constructions/'+encodeURIComponent(sam)+'/address',{address}),
  list:()=>api<{sam:SamCount[];total:number}>('/references'),
  downloadAll:()=>'/api/references/export',
  gallery:(sam:string,cursor?:string|null,limit=60)=>api<CursorPage<Photo>>('/references/'+encodeURIComponent(sam)+'/photos'+query({cursor,limit})),
  setSides:(sam:string,photoIds:string[],side:string|null)=>patch<{updated:number;side:string|null}>(
    '/references/'+encodeURIComponent(sam)+'/sides',{photo_ids:photoIds,side}),
  files:()=>api<{files:ReferenceFile[]}>('/references/files'),
  remove:(id:string)=>del<{deleted?:boolean;queued?:boolean;task_id?:string}>('/references/files/'+id),
  deleteSam:(sam:string)=>del<{deleted?:boolean;queued?:boolean;task_id?:string}>('/references/sam/'+encodeURIComponent(sam)),
  cache:()=>api<{total:number;cached:number;current_signature?:string|null}>('/references/cache/status')
}
