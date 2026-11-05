/** Bounded transfers: report errors immediately and stop a broken initial batch. */
export interface UploadFailure{index:number;error:unknown}
export interface UploadQueueOptions{
  onFailure?:(failure:UploadFailure)=>void
  /** Stop scheduling if N first file transfers fail before any succeeds. */
  haltAfterFailuresWithoutSuccess?:number
}
export async function runUploadQueue(
  count:number,parallel:number,signal:AbortSignal,upload:(index:number)=>Promise<void>,
  options:UploadQueueOptions={}
):Promise<UploadFailure[]>{
  const failures:UploadFailure[]=[]
  let cursor=0,completed=0,halted=false
  const workers=Math.min(count,Math.max(1,Math.floor(parallel)||1))
  const limit=options.haltAfterFailuresWithoutSuccess&&options.haltAfterFailuresWithoutSuccess>0
    ?Math.max(1,Math.floor(options.haltAfterFailuresWithoutSuccess)):Infinity
  async function worker(){
    while(cursor<count&&!signal.aborted&&!halted){
      const index=cursor++
      try{await upload(index);completed++}
      catch(error){
        if(signal.aborted)return
        const failure={index,error}
        failures.push(failure)
        options.onFailure?.(failure)
        // An unavailable server must not trigger 1,330 redundant retries.
        if(completed===0&&failures.length>=limit)halted=true
      }
    }
  }
  // Always drain already started transfers to avoid writes continuing after exit.
  await Promise.all(Array.from({length:workers},()=>worker()))
  if(signal.aborted)throw new DOMException('Загрузка остановлена','AbortError')
  if(halted)throw new Error('Передача остановлена: '+failures.length+
    ' ошибок в начале загрузки, нет ни одного успешно переданного файла.')
  return failures
}
