<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref} from 'vue'

type Mode='idle'|'spinner'|'rotate'|'pulse'|'progress'|'bars'|'waiting'|'success'|'error'
const options:{value:Mode;label:string}[]=[
  {value:'spinner',label:'Вращающееся кольцо'},
  {value:'rotate',label:'Вращение логотипа'},
  {value:'pulse',label:'Пульсация'},
  {value:'progress',label:'Кольцо прогресса'},
  {value:'bars',label:'Движущиеся полоски'},
  {value:'waiting',label:'Жёлтый кружок'},
  {value:'success',label:'Зелёная галочка'},
  {value:'error',label:'Красный крестик'}
]
const mode=ref<Mode>('idle')
const preview=ref('/assets/logo.webp')
const ready=ref(false)
const failed=ref(false)
let icon:HTMLLinkElement|null=null
let originalHref:string|null=null
let originalType:string|null=null
let logo:HTMLImageElement|null=null
let canvas:HTMLCanvasElement|null=null
let ctx:CanvasRenderingContext2D|null=null
let timer:number|undefined
let started=0

function stop(){
  if(timer!==undefined){window.clearInterval(timer);timer=undefined}
}
function restore(){
  stop()
  mode.value='idle'
  if(icon){
    if(originalType===null)icon.removeAttribute('type')
    else icon.setAttribute('type',originalType)
    if(originalHref===null)icon.removeAttribute('href')
    else icon.setAttribute('href',originalHref)
  }
  preview.value=originalHref||'/assets/logo.webp'
}
function render(){
  if(!canvas||!ctx||!logo||!icon||mode.value==='idle')return
  const g=ctx
  const t=(performance.now()-started)/1000
  g.clearRect(0,0,64,64)
  const drawLogo=(size=64,angle=0)=>{
    g.save()
    g.translate(32,32)
    g.rotate(angle)
    g.drawImage(logo!,-size/2,-size/2,size,size)
    g.restore()
  }
  const ring=(start:number,end:number,color:string)=>{
    g.beginPath()
    g.strokeStyle=color
    g.lineWidth=5
    g.lineCap='round'
    g.arc(32,32,28,start,end)
    g.stroke()
  }
  if(mode.value==='spinner'||mode.value==='progress'){
    drawLogo(47)
    ring(0,Math.PI*2,'#666666')
    if(mode.value==='spinner')ring(t*Math.PI*2-Math.PI/2,t*Math.PI*2+Math.PI/3,'#eab308')
    else ring(-Math.PI/2,-Math.PI/2+Math.PI*2*((t%4)/4),'#22c55e')
  }else if(mode.value==='rotate'||mode.value==='pulse'){
    g.fillStyle='#171717'
    g.fillRect(3,3,58,58)
    if(mode.value==='rotate')drawLogo(40,t*Math.PI)
    else drawLogo(42+13*(0.5+0.5*Math.sin(t*Math.PI*2/1.4)))
  }else if(mode.value==='bars'){
    drawLogo()
    g.fillStyle='#171717'
    g.fillRect(9,9,46,46)
    g.fillStyle='#60a5fa'
    for(let i=0;i<3;i++){
      const h=12+26*(0.5+0.5*Math.sin(t*Math.PI*2/0.95-i*1.5))
      g.fillRect(14+i*14,32-h/2,8,h)
    }
  }else{
    drawLogo()
    g.beginPath()
    g.fillStyle='#171717'
    g.arc(47,47,16,0,Math.PI*2)
    g.fill()
    g.beginPath()
    g.fillStyle=mode.value==='success'?'#22c55e':mode.value==='error'?'#ef4444':'#eab308'
    g.arc(47,47,13,0,Math.PI*2)
    g.fill()
    g.strokeStyle='#ffffff'
    g.lineWidth=3.5
    g.lineCap='round'
    g.lineJoin='round'
    g.beginPath()
    if(mode.value==='success'){
      g.moveTo(40,47);g.lineTo(45,52);g.lineTo(54,42);g.stroke()
    }else if(mode.value==='error'){
      g.moveTo(42,42);g.lineTo(52,52);g.moveTo(52,42);g.lineTo(42,52);g.stroke()
    }
  }
  const url=canvas.toDataURL('image/png')
  icon.setAttribute('type','image/png')
  icon.setAttribute('href',url)
  preview.value=url
}
function select(value:Mode){
  if(value==='idle'){restore();return}
  if(!ready.value)return
  stop()
  mode.value=value
  started=performance.now()
  render()
  if(['spinner','rotate','pulse','progress','bars'].includes(value)){
    timer=window.setInterval(render,125)
  }
}
onMounted(()=>{
  icon=document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  if(!icon){failed.value=true;return}
  originalHref=icon.getAttribute('href')
  originalType=icon.getAttribute('type')
  preview.value=originalHref||'/assets/logo.webp'
  canvas=document.createElement('canvas')
  canvas.width=canvas.height=64
  ctx=canvas.getContext('2d')
  if(!ctx){failed.value=true;return}
  logo=new Image()
  logo.onload=()=>{ready.value=true}
  logo.onerror=()=>{failed.value=true}
  logo.src=icon.href
})
onBeforeUnmount(()=>{
  restore()
  if(logo){logo.onload=null;logo.onerror=null}
  logo=null
  canvas=null
  ctx=null
})
</script>

<template>
  <section class="panel stack" aria-labelledby="favicon-test-heading">
    <h2 id="favicon-test-heading">Тест анимаций иконки</h2>
    <p class="meta">Эксперимент: кнопки меняют настоящую иконку вкладки только в этом браузере. Не связаны с обработкой и очередью.</p>
    <div class="row wrap favicon-test-preview">
      <img :src="preview" width="40" height="40" alt="Текущая иконка вкладки"/>
      <div>
        <strong>{{options.find(option=>option.value===mode)?.label||'Обычный логотип MAP'}}</strong>
        <p class="meta">Переключитесь на другую вкладку, чтобы проверить анимацию.</p>
      </div>
    </div>
    <div class="row wrap">
      <button v-for="option in options" :key="option.value" type="button"
        class="btn secondary small" :aria-pressed="mode===option.value"
        :disabled="!ready" @click="select(option.value)">{{option.label}}</button>
    </div>
    <div class="row wrap">
      <button type="button" class="btn secondary" :disabled="mode==='idle'" @click="restore">Сбросить иконку</button>
      <span class="meta">При уходе из настроек иконка восстанавливается.</span>
    </div>
    <p v-if="failed" class="meta" role="alert">Не удалось подготовить тестовую иконку.</p>
  </section>
</template>

<style scoped>
.favicon-test-preview{align-items:center;gap:12px}
.favicon-test-preview img{flex:none;object-fit:contain}
.favicon-test-preview p{margin:3px 0 0}
button[aria-pressed="true"]{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
</style>
