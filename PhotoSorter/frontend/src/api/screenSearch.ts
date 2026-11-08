import {api} from './client'
import type {ScreenPoint} from './references'

export interface MatchPair{reference:[number,number];photo:[number,number];side:number}
export interface DetectedScreen{
 screen_id:string;screen_name:string;reference_id:string;annotation_id:string
 annotation_version:number;status:'found'|'not_found';reason:string
 reference_width?:number;reference_height?:number
 matches?:number;inliers?:number;reprojection_error_px?:number|null
 supported_sides?:number[];corners?:ScreenPoint[];debug_matches?:MatchPair[]
 crop_box?:{x:number;y:number;width:number;height:number};area_px?:number
}
export interface ScreenSearchResult{
 index:number;assigned_sam?:string;status:'not_processed'|'unknown_construction'|'no_annotations'|'not_found'|'found'|'error'
 reason?:string;image_width?:number;image_height?:number;elapsed_seconds?:number
 screens:DetectedScreen[];model_signature?:string
}
const base=(runId:string,index:number)=>
  '/screen-search/runs/'+encodeURIComponent(runId)+'/photos/'+index
export const screenSearchApi={
  model:()=>api<{available:boolean;revision:string;files:Record<string,boolean>}>('/screen-search/model'),
  result:(runId:string,index:number)=>api<ScreenSearchResult>(base(runId,index)),
  crop:(runId:string,index:number,screenId:string)=>
    '/api'+base(runId,index)+'/screens/'+encodeURIComponent(screenId)+'/crop'
}
