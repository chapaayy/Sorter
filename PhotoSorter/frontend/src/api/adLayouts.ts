import {api,patch,del} from './client'
export interface AdLayout {
 id:string;name:string;filename:string;checksum:string;byte_size:number;
 expected_text:string;corrected_text:string|null;ocr_raw_lines:{text:string;score:number;polygon?:number[][]}[];
 ocr_normalized_text:string;preparation_state:'queued'|'running'|'completed'|'failed';
 preparation_stage:string;preparation_progress:number;preparation_error:string|null;
 active:boolean;version:number;image_url:string
}
export interface LayoutMatch {id:string;name:string;score:number;version:number;checksum:string}
export interface AdRecognition {
 index:number;screen_id:string;
 status:'not_processed'|'no_layouts'|'no_match'|'uncertain'|'matched'|'error'
 reason?:string;candidate_id?:string|null;top?:LayoutMatch[];
 margin?:number|null;review_required?:boolean;best_for_layout?:boolean;elapsed_seconds?:number;
 visual_group_id?:string;text_subgroup_id?:string;classification?:'confirmed'|'probable'|'unidentified';
 quality?:{status:string;score:number;version?:string;metrics?:{sharpness:number;exposure:number;glare:number;screen_coverage:number}};
 ocr?:{status:string;reason:string;lines?:string[];matched_terms?:number;total_terms?:number;
  matched_items?:string[];unmatched_items?:string[];text_similarity?:number;
  comparison_confidence?:number;scoring_basis?:string;ambiguous_candidates?:string[]};
 thresholds?:{min_similarity:number;min_margin:number}
}
export const adLayoutApi={
 list:()=>api<{layouts:AdLayout[];total:number}>('/ad-layouts'),
 upload:(file:File,name:string,expectedText:string)=>{
   const data=new FormData();data.append('file',file);data.append('name',name)
   data.append('expected_text',expectedText)
   return api<{id:string;version:number}>('/ad-layouts',{method:'POST',body:data})
 },
 edit:(item:AdLayout,name:string,expectedText:string,active:boolean)=>
   patch<{id:string;version:number}>('/ad-layouts/'+encodeURIComponent(item.id),{
     name,expected_text:expectedText,active,version:item.version
   }),
 replaceImage:(item:AdLayout,file:File)=>{
   const data=new FormData()
   data.append('file',file);data.append('version',String(item.version))
   return api<{id:string;version:number;preparation_state:string}>(
     '/ad-layouts/'+encodeURIComponent(item.id)+'/image',{method:'PUT',body:data})
 },
 remove:(id:string)=>del<{deleted:boolean}>('/ad-layouts/'+encodeURIComponent(id)),
 recognized:(runId:string,index:number,screenId:string)=>
   api<AdRecognition>('/ad-recognition/runs/'+encodeURIComponent(runId)+'/photos/'+index+
     '/screens/'+encodeURIComponent(screenId)),
 models:()=>api<{dino:{available:boolean};ocr:{available:boolean}}>('/ad-recognition/models')
}
