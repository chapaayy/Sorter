import {api,query} from './client'
import type {LogEntry} from '../types/api'
export interface LogFilters{cursor?:string|null;limit?:number;tail_mode?:boolean;model?:string;level?:string;source?:string;search?:string}
export const logApi={
  runs:()=>api<{runs:{id:string;started_at?:string|null}[]}>('/logs/runs'),
  page:(id:string,filters:LogFilters)=>api<{events:LogEntry[];next_cursor:string|null}>('/logs/'+encodeURIComponent(id)+'/page'+query({...filters})),
  usage:()=>api<{bytes:number;budget_bytes:number;run_budget_bytes:number}>('/logs/usage')
}
