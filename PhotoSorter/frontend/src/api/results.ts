import {api,query} from './client'
import type {ResultPhoto,CursorPage,Run,DeletionProgress} from '../types/api'
export interface PublishedResult { can_media?:boolean;can_zip?:boolean;
  id:string; batch_id?:string; owner_id?:string; status:Run['status']; display_name:string; finished_at?:string|null
  started_at?:string|null;actual_started_at?:string|null;actual_finished_at?:string|null
  photo_count?:number|null;groups?:number|null;uncertain?:number|null;overall_percent?:number|null
  thumbnail_url?:string|null;can_history?:boolean;can_open?:boolean
  delete_state?:string|null;deletion_progress?:DeletionProgress|null
}
export const resultApi={
  catalog:(limit=30,offset=0,search='')=>api<{items:PublishedResult[];has_more:boolean}>('/results/catalog'+query({limit,offset,search})),
  published:(id:string)=>api<PublishedResult>('/results/'+encodeURIComponent(id)),
  one:(id:string)=>api<Run>('/results/'+encodeURIComponent(id)),
  sam:(id:string)=>api<Record<string,number>>('/results/'+encodeURIComponent(id)+'/sam'),
  groups:(id:string)=>api<Record<string,number>>('/results/'+encodeURIComponent(id)+'/groups'),
  photos:(id:string,options:{sam?:string;group?:string;cursor?:string|null;limit?:number})=>
    api<CursorPage<ResultPhoto>>('/results/'+encodeURIComponent(id)+'/photos'+query(options)),
  download:(id:string,sam?:string)=>'/api/download/'+encodeURIComponent(id)+query({sam})
}
