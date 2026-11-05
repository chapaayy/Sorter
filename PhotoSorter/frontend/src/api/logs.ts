import {api,query} from './client'
import type {LogEntry} from '../types/api'
export interface LogFilters{cursor?:string|null;limit?:number;tail_mode?:boolean;model?:string;level?:string;source?:string;search?:string}
export const logApi={
  page:(id:string,filters:LogFilters)=>api<{events:LogEntry[];next_cursor:string|null}>('/logs/'+encodeURIComponent(id)+'/page'+query({...filters})),
  usage:()=>api<{bytes:number;budget_bytes:number;run_budget_bytes:number}>('/logs/usage')
}
