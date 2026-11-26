export type OwnTaskState='running'|'stopping'|'queued'|'blocked'|'completed'|'completed_with_errors'|'failed'|'interrupted'|'stopped'
export interface OwnTask {seq:number;run_id:string;state:OwnTaskState;progress:number|null;finished_at:string|null}
export interface OwnWorkStatus {account_id:string;sampled_at:string;tasks:OwnTask[]}
export type IconState=
  |{kind:'idle'|'queued'|'paused'|'success'|'error'}
  |{kind:'running';run:string;progress:number|null}
export const idleIcon:IconState={kind:'idle'}
function terminal(task:OwnTask):'error'|'success'|'paused'|null{
  if(['failed','interrupted','completed_with_errors'].includes(task.state))return 'error'
  if(task.state==='completed')return 'success'
  if(task.state==='stopped')return 'paused'
  return null
}
function progress(value:number|null):number|null{
  return typeof value==='number'&&Number.isFinite(value)?Math.max(0,Math.min(1,value/100)):null
}

/** Local, per authenticated session. Historic outcomes are a baseline, not notifications. */
export class FaviconState {
  private baseline:number|null=null
  private seen=new Set<string>()
  private observed=new Set<string>()
  private error:OwnTask|null=null
  private success:OwnTask|null=null
  private paused:OwnTask|null=null
  private active:OwnTask[]=[]
  update(snapshot:OwnWorkStatus):IconState{
    const initial=this.baseline===null
    if(initial)this.baseline=Date.parse(snapshot.sampled_at)
    const next=snapshot.tasks.filter(task=>['running','stopping','queued','blocked'].includes(task.state))
    const newWork=next.some(task=>!this.observed.has(task.run_id))
    if(newWork){this.success=null;this.paused=null}
    for(const task of next)this.observed.add(task.run_id)
    for(const task of snapshot.tasks){
      const outcome=terminal(task)
      if(!outcome||!task.finished_at)continue
      const key=task.run_id+':'+task.state+':'+task.finished_at
      if(this.seen.has(key))continue
      this.seen.add(key)
      if(initial||(!this.observed.has(task.run_id)&&!(Date.parse(task.finished_at)>this.baseline!)))continue
      if(outcome==='error')this.error=task
      else if(outcome==='paused')this.paused=task
      else this.success=task
    }
    this.active=next
    return this.state()
  }
  state():IconState{
    const running=this.active.find(task=>task.state==='running')
    if(running)return {kind:'running',run:running.run_id,progress:progress(running.progress)}
    if(this.error)return {kind:'error'}
    if(this.active.some(task=>task.state==='queued'||task.state==='blocked'))return {kind:'queued'}
    if(this.paused||this.active.some(task=>task.state==='stopping'))return {kind:'paused'}
    if(this.success)return {kind:'success'}
    return idleIcon
  }
  acknowledgeSuccess(){this.success=null}
  acknowledgeHistory(){this.error=null;this.success=null;this.paused=null}
  acknowledgeRun(run:string){
    if(this.error?.run_id===run)this.error=null
    if(this.success?.run_id===run)this.success=null
    if(this.paused?.run_id===run)this.paused=null
  }
}
