import {api,post,query} from './client'
import type {PublishedResult} from './results'

export interface ManagedUser {id:number;email:string;created_at:string}
export interface NewUser {email:string;password:string;confirmation:string;run_ids:string[]}

export const adminUsers={
  list:(offset=0)=>api<{items:ManagedUser[];has_more:boolean}>('/admin/users'+query({offset})),
  create:(payload:NewUser)=>post<ManagedUser>('/admin/users',payload),
  grants:(id:number)=>api<{items:PublishedResult[]}>('/admin/users/'+id+'/grants'),
  save:(id:number,run_ids:string[])=>api<{items:PublishedResult[]}>('/admin/users/'+id+'/grants',{
    method:'PUT',body:JSON.stringify({run_ids})
  })
}
