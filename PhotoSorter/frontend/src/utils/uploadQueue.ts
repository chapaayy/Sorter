/** Run independent uploads with bounded concurrency; drain workers before returning. */
export interface UploadFailure{index:number;error:unknown}

export async function runUploadQueue(
  count:number,parallel:number,signal:AbortSignal,upload:(index:number)=>Promise<void>
):Promise<UploadFailure[]>{
  const failures:UploadFailure[]=[]
  let cursor=0
  const workers=Math.min(count,Math.max(1,Math.floor(parallel)||1))
  async function worker(){
    while(cursor<count&&!signal.aborted){
      const index=cursor++
      try{await upload(index)}
      catch(error){
        if(signal.aborted)return
        failures.push({index,error})
      }
    }
  }
  // Wait for ALL in-flight requests, even when another file fails.
  await Promise.all(Array.from({length:workers},()=>worker()))
  if(signal.aborted)throw new DOMException('Загрузка остановлена','AbortError')
  return failures
}
