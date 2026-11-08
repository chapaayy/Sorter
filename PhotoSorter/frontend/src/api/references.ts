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
export interface ScreenPoint{x:number;y:number}
export interface ScreenAnnotation{
 id:string;reference_id:string;corners:ScreenPoint[];band_width_px:number
 version:number;source_sha256:string;image_width:number;image_height:number
}
export interface ScreenDefinition{id:string;name:string;annotations:ScreenAnnotation[]}
export interface ScreenPhotoMetadata{reference_id:string;width:number;height:number;source_sha256:string}
export interface ScreenGeometry{corners:ScreenPoint[];band_width_px:number}
export interface NewScreenAnnotation extends ScreenGeometry{
 reference_id:string;screen_id:string|null;screen_name:string|null
}
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
  cache:()=>api<{total:number;cached:number;current_signature?:string|null}>('/references/cache/status'),
  screens:(sam:string)=>api<{screens:ScreenDefinition[]}>('/references/'+encodeURIComponent(sam)+'/screens'),
  screenPhoto:(sam:string,id:string)=>api<ScreenPhotoMetadata>('/references/'+encodeURIComponent(sam)+'/photos/'+encodeURIComponent(id)+'/screen-metadata'),
  createAnnotation:(sam:string,value:NewScreenAnnotation)=>post<{id:string;screen_id:string;version:number}>('/references/'+encodeURIComponent(sam)+'/screen-annotations',value),
  updateAnnotation:(sam:string,id:string,value:ScreenGeometry&{version:number})=>patch<{id:string;screen_id:string;version:number}>('/references/'+encodeURIComponent(sam)+'/screen-annotations/'+encodeURIComponent(id),value),
  deleteAnnotation:(sam:string,id:string)=>del<{deleted:boolean}>('/references/'+encodeURIComponent(sam)+'/screen-annotations/'+encodeURIComponent(id)),
  deleteScreen:(sam:string,id:string)=>del<{deleted:boolean}>('/references/'+encodeURIComponent(sam)+'/screens/'+encodeURIComponent(id))
}
