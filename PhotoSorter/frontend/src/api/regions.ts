import {api,post} from './client'

export interface Region {code:string;constructions:number}
export const regionApi={
  list:()=>api<{regions:Region[]}>('/regions'),
  create:(code:string)=>post<{code:string}>('/regions',{code})
}
