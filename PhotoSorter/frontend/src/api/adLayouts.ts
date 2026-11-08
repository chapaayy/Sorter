import {api,patch,del} from './client'
export interface AdLayout {
 id:string;name:string;filename:string;checksum:string;byte_size:number;
 expected_text:string;active:boolean;version:number;image_url:string
}
export interface LayoutMatch {id:string;name:string;score:number;version:number;checksum:string}
export interface AdRecognition {
 index:number;screen_id:string;
 status:'not_processed'|'no_layouts'|'no_match'|'uncertain'|'matched'|'error'
 reason?:string;candidate_id?:string|null;top?:LayoutMatch[];
 margin?:number|null;review_required?:boolean;best_for_layout?:boolean;elapsed_seconds?:number;
 quality?:{status:string;score:number;version?:string;metrics?:{sharpness:number;exposure:number;glare:number;screen_coverage:number}};
 ocr?:{status:string;reason:string;lines?:string[];matched_terms?:number;total_terms?:number};
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
 remove:(id:string)=>del<{deleted:boolean}>('/ad-layouts/'+encodeURIComponent(id)),
 recognized:(runId:string,index:number,screenId:string)=>
   api<AdRecognition>('/ad-recognition/runs/'+encodeURIComponent(runId)+'/photos/'+index+
     '/screens/'+encodeURIComponent(screenId)),
 models:()=>api<{dino:{available:boolean};ocr:{available:boolean}}>('/ad-recognition/models')
}
