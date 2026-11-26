import {idleIcon,type IconState} from './faviconState'

const SIZE=64
const YELLOW='#eab308',GREEN='#22c55e',RED='#ef4444',GRAY='#888888',DARK='#151515'
const clamp=(x:number)=>Math.max(0,Math.min(1,x))
const ease=(x:number)=>{x=clamp(x);return x*x*(3-2*x)}
const mix=(a:number,b:number,t:number)=>a+(b-a)*t

/** A bounded, local renderer. No network requests for animation frames. */
export class FaviconRenderer {
  private link=document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  private originalHref=this.link?.getAttribute('href')??null
  private originalType=this.link?.getAttribute('type')??null
  private canvas=document.createElement('canvas')
  private g:CanvasRenderingContext2D|null
  private logo=new Image()
  private motion=window.matchMedia('(prefers-reduced-motion: reduce)')
  private timer:number|undefined
  private ready=false
  private disposed=false
  private state:IconState=idleIcon
  private shown=0
  private logoScale=1
  private lastUrl=''
  constructor(){
    this.canvas.width=this.canvas.height=SIZE
    this.g=this.canvas.getContext('2d')
    this.logo.onload=()=>{if(!this.disposed){this.ready=true;this.paintCurrent()}}
    if(this.link)this.logo.src=this.link.href
    this.motion.addEventListener('change',this.motionChanged)
  }
  private motionChanged=()=>{this.stop();this.paintCurrent()}
  private stop(){if(this.timer!==undefined){window.clearInterval(this.timer);this.timer=undefined}}
  private restore(){
    this.lastUrl=''
    if(!this.link)return
    if(this.originalHref===null)this.link.removeAttribute('href')
    else this.link.setAttribute('href',this.originalHref)
    if(this.originalType===null)this.link.removeAttribute('type')
    else this.link.setAttribute('type',this.originalType)
  }
  private logoAt(scale:number){
    const g=this.g!
    const size=40*scale
    g.drawImage(this.logo,20-size/2,20-size/2,size,size)
    this.logoScale=scale
  }
  private begin(){
    if(!this.g||!this.ready||!this.link||this.disposed)return false
    this.g.setTransform(SIZE/40,0,0,SIZE/40,0,0)
    this.g.clearRect(0,0,40,40)
    return true
  }
  private publish(){
    try{
      const url=this.canvas.toDataURL('image/png')
      if(url!==this.lastUrl){this.link!.setAttribute('type','image/png');this.link!.setAttribute('href',url);this.lastUrl=url}
    }catch{this.stop();this.restore()}
  }
  private ring(p:number|null,scale:number,color=YELLOW,angle=0,alpha=1){
    if(!this.begin())return
    const g=this.g!
    this.logoAt(scale);g.save();g.globalAlpha=alpha
    g.lineWidth=3.5;g.lineCap='round';g.strokeStyle='#666666'
    g.beginPath();g.arc(20,20,18,0,Math.PI*2);g.stroke()
    if(p===null||p>0){
      const start=-Math.PI/2+(p===null?angle:0)
      g.beginPath();g.arc(20,20,18,start,start+Math.PI*2*(p===null?.23:p))
      g.strokeStyle=color;g.stroke()
    }
    g.restore();this.publish()
  }
  private symbol(kind:IconState['kind'],x:number,y:number,opacity=1){
    const g=this.g!
    g.save();g.globalAlpha=opacity;g.translate(x,y)
    g.strokeStyle='#fff';g.lineWidth=2.3;g.lineCap='round';g.lineJoin='round'
    g.beginPath()
    if(kind==='success'){g.moveTo(-4,0);g.lineTo(-1,3);g.lineTo(4,-3.8)}
    else if(kind==='error'){g.moveTo(-3.3,-3.3);g.lineTo(3.3,3.3);g.moveTo(3.3,-3.3);g.lineTo(-3.3,3.3)}
    else if(kind==='paused'){g.moveTo(-2,-3.5);g.lineTo(-2,3.5);g.moveTo(2,-3.5);g.lineTo(2,3.5)}
    g.stroke();g.restore()
  }
  private badge(kind:IconState['kind']){
    if(!this.begin())return
    const g=this.g!
    this.logoAt(1)
    g.beginPath();g.arc(31,31,8.3,0,Math.PI*2)
    g.fillStyle=kind==='success'?GREEN:kind==='error'?RED:kind==='paused'?GRAY:YELLOW
    g.fill();g.lineWidth=1.2;g.strokeStyle=DARK;g.stroke()
    this.symbol(kind,31,31);this.publish()
  }
  private morph(t:number){
    if(!this.begin())return
    const g=this.g!
    const p=ease(t),x=mix(20,31,p),y=mix(20,31,p)
    const outer=mix(19.75,8.3,p),inner=16.25*(1-ease(p*1.9))
    this.logoAt(mix(.75,1,p))
    g.beginPath();g.arc(x,y,outer,0,Math.PI*2)
    if(inner>.001){g.moveTo(x+inner,y);g.arc(x,y,inner,0,Math.PI*2)}
    g.fillStyle=GREEN;g.fill('evenodd')
    const alpha=ease((p-.8)/.2)
    if(alpha>0){
      g.save();g.globalAlpha=alpha;g.beginPath();g.arc(x,y,outer,0,Math.PI*2)
      g.strokeStyle=DARK;g.lineWidth=1.2;g.stroke();g.restore()
      this.symbol('success',x,y,alpha)
    }
    this.publish()
  }
  private animate(duration:number,draw:(elapsed:number)=>void,loop=false){
    const start=performance.now()
    const frame=()=>{
      const elapsed=performance.now()-start
      draw(loop?elapsed:Math.min(duration,elapsed))
      if(!loop&&elapsed>=duration)this.stop()
    }
    // setInterval can run in background tabs (subject to browser throttling).
    this.timer=window.setInterval(frame,1000/30)
    frame()
  }
  private paintCurrent(){
    if(this.state.kind==='idle'){this.shown=0;this.logoScale=1;this.restore()}
    else if(this.state.kind==='running'){
      const p=this.state.progress
      this.shown=p??0
      if(p===null&&!this.motion.matches)this.animate(1000,t=>this.ring(null,.75,YELLOW,t*Math.PI*2/1000),true)
      else this.ring(p,.75)
    }else this.badge(this.state.kind)
  }
  set(next:IconState){
    const prev=this.state
    if(prev.kind===next.kind&&(next.kind!=='running'||(prev.kind==='running'&&prev.run===next.run&&prev.progress===next.progress)))return
    this.stop();this.state=next
    if(!this.ready||this.motion.matches){this.paintCurrent();return}
    if(next.kind==='running'){
      const same=prev.kind==='running'&&prev.run===next.run
      const from=same?this.shown:0,scale=this.logoScale,target=next.progress
      if(target===null){
        this.animate(1000,t=>this.ring(null,mix(scale,.75,ease(t/300)),YELLOW,t*Math.PI*2/1000),true)
      }else{
        this.animate(450,t=>{
          const p=ease(t/450);this.shown=mix(from,target,p)
          this.ring(this.shown,mix(scale,.75,p),YELLOW,0,same?1:p)
        })
      }
    }else if(next.kind==='success'&&prev.kind==='running'){
      const from=this.shown,scale=this.logoScale
      this.animate(1100,t=>{
        if(t<180){this.ring(mix(from,1,ease(t/180)),mix(scale,.75,ease(t/180)),YELLOW)}
        else if(t<350)this.ring(1,.75,GREEN)
        else this.morph((t-350)/750)
      })
    }else this.paintCurrent()
  }
  reset(){this.stop();this.state=idleIcon;this.paintCurrent()}
  dispose(){this.reset();this.disposed=true;this.logo.onload=null;this.motion.removeEventListener('change',this.motionChanged)}
}
