import {ApiError} from '../api/client'

export type TransferState={state:'waiting'|'active';attempt:number;delayMs?:number}

/** Network outages may last minutes (VPN handover). Pause always interrupts sleep.
 * 5xx/429 use bounded retries to avoid hiding persistent server failures.
 */
export async function withUploadRetry<T>(
  request:()=>Promise<T>,signal:AbortSignal,onState?:(state:TransferState)=>void
):Promise<T>{
  let attempt=0
  while(true){
    if(signal.aborted)throw new DOMException('Загрузка остановлена','AbortError')
    try{
      const value=await request()
      if(signal.aborted)throw new DOMException('Загрузка остановлена','AbortError')
      if(attempt)onState?.({state:'active',attempt})
      return value
    }catch(error){
      if(signal.aborted)throw new DOMException('Загрузка остановлена','AbortError')
      if(!(error instanceof ApiError))throw error
      const isOffline=error.status===0
      const temporary=[408,429,500,502,503,504].includes(error.status)
      if(!isOffline&&!temporary)throw error
      if(temporary&&attempt>=6)throw error
      attempt++
      const delayMs=Math.min(30000,1000*2**Math.min(attempt-1,5))
      onState?.({state:'waiting',attempt,delayMs})
      await delayOrOnline(delayMs,signal)
    }
  }
}

function delayOrOnline(ms:number,signal:AbortSignal):Promise<void>{
  return new Promise((resolve,reject)=>{
    if(signal.aborted){reject(new DOMException('Загрузка остановлена','AbortError'));return}
    let timer:ReturnType<typeof setTimeout>
    let settled=false
    const clear=()=>{
      if(settled)return false
      settled=true
      clearTimeout(timer)
      signal.removeEventListener('abort',onAbort)
      if(typeof window!=='undefined')window.removeEventListener('online',onOnline)
      return true
    }
    const onAbort=()=>{if(clear())reject(new DOMException('Загрузка остановлена','AbortError'))}
    const onOnline=()=>{if(clear())resolve()}
    signal.addEventListener('abort',onAbort,{once:true})
    if(typeof window!=='undefined')window.addEventListener('online',onOnline,{once:true})
    timer=setTimeout(()=>{if(clear())resolve()},ms)
  })
}
