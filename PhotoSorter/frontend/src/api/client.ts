export class ApiError extends Error {
  constructor(public status:number,message:string){ super(message); this.name='ApiError' }
}
let unauthorized:(()=>void)|undefined
export function onUnauthorized(handler:()=>void){unauthorized=handler}
export function query(params:Record<string,string|number|boolean|null|undefined>):string{
  const q=new URLSearchParams()
  for(const [k,v] of Object.entries(params))if(v!=='' && v!=null)q.set(k,String(v))
  return q.size?'?'+q.toString():''
}
export async function api<T>(path:string,options:RequestInit={}):Promise<T>{
  const headers=new Headers(options.headers)
  if(options.body!=null && typeof options.body==='string' && !headers.has('Content-Type'))headers.set('Content-Type','application/json')
  let response:Response
  try{response=await fetch('/api'+path,{credentials:'same-origin',cache:'no-store',...options,headers})}
  catch{throw new ApiError(0,'Нет соединения с сервером. Проверьте сеть.')}
  if(!response.ok){
    let detail='Ошибка сервера ('+response.status+')'
    try{const data=await response.json() as {detail?:unknown};if(typeof data.detail==='string')detail=data.detail;else if(data.detail)detail=JSON.stringify(data.detail)}
    catch{ /* non-JSON */ }
    if(response.status===401)unauthorized?.()
    throw new ApiError(response.status,detail)
  }
  if(response.status===204)return undefined as T
  return response.json() as Promise<T>
}
export const post=<T>(p:string,b:unknown)=>api<T>(p,{method:'POST',body:JSON.stringify(b)})
export const patch=<T>(p:string,b:unknown)=>api<T>(p,{method:'PATCH',body:JSON.stringify(b)})
export const del=<T>(p:string)=>api<T>(p,{method:'DELETE'})
