import {api,query} from './client'
import type {ResultPhoto,CursorPage,Run} from '../types/api'
export const resultApi={
  one:(id:string)=>api<Run>('/results/'+encodeURIComponent(id)),
  sam:(id:string)=>api<Record<string,number>>('/results/'+encodeURIComponent(id)+'/sam'),
  groups:(id:string)=>api<Record<string,number>>('/results/'+encodeURIComponent(id)+'/groups'),
  photos:(id:string,options:{sam?:string;group?:string;cursor?:string|null;limit?:number})=>
    api<CursorPage<ResultPhoto>>('/results/'+encodeURIComponent(id)+'/photos'+query(options)),
  download:(id:string,sam?:string)=>'/api/download/'+encodeURIComponent(id)+query({sam})
}
