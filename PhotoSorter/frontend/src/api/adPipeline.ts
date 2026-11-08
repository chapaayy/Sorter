import {api,patch} from './client'
export interface BestPhoto {
 index:number;assigned_sam:string;screen_id:string;screen_name?:string
 candidate_id:string;layout_name:string;layout_version:number
 review_required:boolean;quality:{status:string;score:number;metrics?:Record<string,number>}
 classification?:'confirmed'|'probable'|'unidentified';visual_group_id?:string
 text_subgroup_id?:string;text_subgroup_status?:string
 ocr?:{status:string;reason:string;matched_terms?:number;total_terms?:number;
  text_similarity?:number};ocr_selection_score?:number;selection_score?:number;
 selection_basis?:string;source_xfeat_signature?:string
}
export interface BestSummary {
 status:'not_processed'|'completed';run_id:string;best:BestPhoto[]
 total_photos?:number;screens_found?:number;recognized?:number
 review_required?:number;errors?:number;reference_version?:number
 visual_group_count?:number;text_subgroup_count?:number
 text_confirmed?:number;text_probable?:number;text_unidentified?:number
}
export interface AdPipelineSettings {
 enabled:boolean;grouping_threshold:number;matching_threshold:number;
 applies:string;default_safe:boolean
}
export const adPipelineApi={
 settings:()=>api<AdPipelineSettings>('/ad-pipeline/settings'),
 update:(enabled:boolean)=>patch<AdPipelineSettings>('/ad-pipeline/settings',{enabled}),
 updateThresholds:(grouping_threshold:number,matching_threshold:number)=>
   patch<AdPipelineSettings>('/ad-pipeline/settings',{grouping_threshold,matching_threshold}),
 best:(id:string)=>api<BestSummary>('/ad-pipeline/runs/'+encodeURIComponent(id)+'/best')
}
