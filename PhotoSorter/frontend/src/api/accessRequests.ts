import {api,post,query} from './client'
import type {PublishedResult} from './results'
export type RequestStatus='pending'|'approved'|'rejected'
export interface AccessRequest {
  id:string; email:string; comment:string; status:RequestStatus; created_at:string; decided_at:string|null
}
export const accessRequests={
  list:(status:RequestStatus,offset=0)=>api<{items:AccessRequest[];has_more:boolean}>(
    '/admin/access-requests'+query({status,offset})),
  decide:(id:string,approved:boolean,run_ids:string[])=>post<AccessRequest>(
    '/admin/access-requests/'+encodeURIComponent(id)+'/decision',{approved,run_ids}),
  grants:(id:string)=>api<{items:PublishedResult[]}>('/admin/access-requests/'+encodeURIComponent(id)+'/grants'),
  save:(id:string,run_ids:string[])=>api<{items:PublishedResult[]}>('/admin/access-requests/'+encodeURIComponent(id)+'/grants',
    {method:'PUT',body:JSON.stringify({run_ids})})
}
