import {api,post,query} from './client'
import type {StorageCounter,StorageBudget} from '../types/api'
export type Level='none'|'own'|'all'|'granted'
export type Permissions=Record<string,Level>
export interface PermissionInfo{label:string;group:string;requires?:string}
export interface Role{id:string;name:string;description:string;permissions:Permissions;users:number}
export interface Account{id:number;username:string;display_name:string;role_id:string;role_name:string;blocked:boolean;created_at:string;last_login_at:string|null;storage_limit_bytes?:number|null;usage?:StorageCounter|null;quota?:StorageBudget}
export interface AccountDetail extends Account{permission_overrides:Permissions;role_permissions:Permissions;permissions:Permissions;sessions:Array<{session_id:string;created_at:string|null;expires_at:string}>}
export interface RolePayload{name:string;description:string;permissions:Permissions}
export const accountsApi={
 list:(search='',offset=0)=>api<{items:Account[];has_more:boolean;stats:{total:number;active:number;blocked:number};partial:boolean;sampled_at:string|null}>('/admin/accounts'+query({search,offset})),
 roles:()=>api<{items:Role[];catalog:Record<string,PermissionInfo>}>('/admin/accounts/roles'),
 detail:(id:number)=>api<AccountDetail>('/admin/accounts/'+id),
 edit:(id:number,value:{display_name:string;role_id:string;overrides:Permissions})=>api<AccountDetail>('/admin/accounts/'+id,{method:'PUT',body:JSON.stringify(value)}),
 saveRole:(id:string|null,value:RolePayload)=>id?api<{id:string}>('/admin/accounts/roles/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify(value)}):post<{id:string}>('/admin/accounts/roles',value),
 deleteRole:(id:string,replacement:string|null)=>post('/admin/accounts/roles/'+encodeURIComponent(id)+'/delete',{confirmed:true,replacement}),
 security:(id:number,action:string,password?:string,session_id?:string)=>post('/admin/accounts/'+id+'/security',{action,confirmed:true,password,session_id}),
 registration:()=>api<{enabled:boolean;pending:number}>('/admin/accounts/registration'),
 setRegistration:(enabled:boolean)=>api<{enabled:boolean;pending:number}>('/admin/accounts/registration',{method:'PUT',body:JSON.stringify({enabled})}),
 events:()=>api<{items:Array<{id:number;at:string;actor:string;target:string;action:string}>}>('/admin/accounts/events')
}
