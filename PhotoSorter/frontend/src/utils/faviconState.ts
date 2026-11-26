export type OwnTaskState='running'|'stopping'|'queued'|'blocked'|'completed'|'completed_with_errors'|'failed'|'interrupted'|'stopped'
export interface OwnTask {kind?:'fo'|'media'|'reference'|'reference-delete'|'cleanup'|'zip';seq:number;run_id:string;state:OwnTaskState;progress:number|null;finished_at:string|null}
export interface OwnWorkStatus {account_id:string;username?:string;sampled_at:string;tasks:OwnTask[]}
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
    for(const task of [...snapshot.tasks].sort((a,b)=>Date.parse(a.finished_at||'1970-01-01')-Date.parse(b.finished_at||'1970-01-01'))){
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
    const priority=['fo','media','reference','reference-delete','cleanup','zip']
    const running=this.active.filter(task=>task.state==='running')
      .sort((a,b)=>priority.indexOf(a.kind||'fo')-priority.indexOf(b.kind||'fo')||a.seq-b.seq)[0]
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

/** Server work takes precedence over browser-local transfers. Never hide active
 * work with a previous success; an error remains higher priority than waiting. */
export function combineActivity(server:IconState,local:IconState):IconState{
  const rank:Record<IconState['kind'],number>={running:5,error:4,queued:3,paused:2,success:1,idle:0}
  return rank[server.kind]>=rank[local.kind]?server:local
}
