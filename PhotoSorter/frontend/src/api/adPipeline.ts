import {api,patch} from './client'
export interface BestPhoto {
 index:number;assigned_sam:string;screen_id:string;screen_name?:string
 candidate_id:string;layout_name:string;layout_version:number
 review_required:boolean;quality:{status:string;score:number;metrics?:Record<string,number>}
 ocr?:{status:string;reason:string};source_xfeat_signature?:string
}
export interface BestSummary {
 status:'not_processed'|'completed';run_id:string;best:BestPhoto[]
 total_photos?:number;screens_found?:number;recognized?:number
 review_required?:number;errors?:number;reference_version?:number
}
export interface AdPipelineSettings {
 enabled:boolean;applies:string;default_safe:boolean
}
export const adPipelineApi={
 settings:()=>api<AdPipelineSettings>('/ad-pipeline/settings'),
 update:(enabled:boolean)=>patch<AdPipelineSettings>('/ad-pipeline/settings',{enabled}),
 best:(id:string)=>api<BestSummary>('/ad-pipeline/runs/'+encodeURIComponent(id)+'/best')
}
