<script setup lang="ts">
import {computed,ref} from 'vue'
import {uploadOne,ALLOWED} from '../../utils/upload'
import type {UploadEntry} from '../../utils/upload'
import {bytes,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
const props=defineProps<{selectedSam:string;disabled:boolean}>()
const emit=defineEmits<{(e:'finished'):void}>()
type Task={sam:string;entry:UploadEntry}
const tasks=ref<Task[]>([]),busy=ref(false),error=ref(''),done=ref(0),sent=ref(0)
const total=computed(()=>tasks.value.reduce((sum,t)=>sum+t.entry.file.size,0))
const percent=computed(()=>total.value?Math.round(100*sent.value/total.value):0)
let controller:AbortController|null=null
function chooseFiles(event:Event){
  const input=event.target as HTMLInputElement
  tasks.value=Array.from(input.files||[]).filter(f=>ALLOWED.test(f.name)).map(file=>({sam:props.selectedSam,entry:{file,relative:file.name}}))
  error.value=tasks.value.length?'':'Нет поддерживаемых изображений'
  input.value=''
}
function chooseDirectory(event:Event){
  const input=event.target as HTMLInputElement
  const list:Task[]=[]
  for(const file of Array.from(input.files||[])){
    if(!ALLOWED.test(file.name))continue
    const segments=file.webkitRelativePath.split('/').filter(Boolean)
    const sam=segments.find(s=>/^SAM-\d{4}(?:$|-)/i.test(s))
    if(!sam)continue
    list.push({sam,entry:{file,relative:file.webkitRelativePath}})
  }
  tasks.value=list
  error.value=list.length?'':'Не найдены папки SAM-xxxx с изображениями'
  input.value=''
}
async function upload(){
  if(!tasks.value.length||busy.value||props.disabled)return
  busy.value=true;error.value='';done.value=0;sent.value=0;controller=new AbortController()
  const amounts=tasks.value.map(()=>0),queue=tasks.value.map((_,i)=>i)
  try{
    async function worker(){
      while(queue.length){
        const i=queue.shift()
        if(i===undefined)break
        const item=tasks.value[i]
        if(!item)continue
        if(controller?.signal.aborted)throw new DOMException('Остановлено','AbortError')
        await uploadOne({kind:'reference',sam:item.sam},item.entry,controller!.signal,n=>{
          amounts[i]=n;sent.value=amounts.reduce((a,b)=>a+b,0)
        })
        done.value++
      }
    }
    await Promise.all(Array.from({length:Math.min(3,queue.length)},worker))
    tasks.value=[];emit('finished')
  }catch(e){error.value=controller.signal.aborted?'Передача приостановлена — выберите файлы ещё раз для докачки.':errorText(e)}
  finally{busy.value=false;controller=null}
}
</script>
<template>
<section class="panel stack">
  <div class="panel-header"><h2>Загрузка Образцов</h2><span class="status">Общая библиотека SAM</span></div>
  <div v-if="disabled" class="alert">Редактирование Образцов заблокировано, пока MegaLoc выполняет обработку или ожидает запуск.</div>
  <div class="grid2">
    <label class="upload-drop" :style="{opacity:disabled?'.5':'1'}">
      <input type="file" multiple accept="image/*" :disabled="disabled||!selectedSam||busy" @change="chooseFiles"/>
      <strong>+ Добавить в {{selectedSam||'SAM'}}</strong>
      <div class="meta">Обычные файлы</div>
    </label>
    <label class="upload-drop" :style="{opacity:disabled?'.5':'1'}">
      <input type="file" webkitdirectory directory multiple :disabled="disabled||busy" @change="chooseDirectory"/>
      <strong>▤ Загрузить библиотеку</strong>
      <div class="meta">Папки с именами SAM-xxxx</div>
    </label>
  </div>
  <div v-if="tasks.length" class="row between wrap">
    <span>{{tasks.length}} файлов · {{bytes(total)}} · {{new Set(tasks.map(t=>t.sam)).size}} SAM</span>
    <div class="row"><UiButton v-if="busy" kind="danger" @click="controller?.abort()">Пауза</UiButton><UiButton v-else kind="primary" :disabled="disabled" @click="upload">Начать загрузку</UiButton></div>
  </div>
  <div v-if="busy" class="stack-sm">
    <div class="row between meta"><span>{{done}} из {{tasks.length}} файлов</span><span>{{percent}}%</span></div>
    <div class="progress-track"><span class="progress-fill" :style="{width:percent+'%'}"/></div>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
</section>
</template>
