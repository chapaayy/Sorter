<script setup lang="ts">
import {computed,onMounted,ref,watch,nextTick} from 'vue'
import {useRoute} from 'vue-router'
import {runApi} from '../../api/runs'
import {logApi} from '../../api/logs'
import {usePolling} from '../../composables/usePolling'
import {bytes,date,errorText} from '../../utils/format'
import type {Run,LogEntry} from '../../types/api'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import {useNoticeStore} from '../../stores/notice'
const route=useRoute(),notice=useNoticeStore()
const runs=ref<Run[]>([]),selected=ref(''),level=ref(''),source=ref(''),search=ref('')
const events=ref<LogEntry[]>([]),cursor=ref<string|null>(null),loading=ref(false),error=ref(''),following=ref(true),tailMode=ref(true),host=ref<HTMLElement|null>(null)
let sequence=0,searchTimer:ReturnType<typeof setTimeout>|undefined
const filters=computed(()=>({level:level.value||undefined,source:source.value||undefined,search:search.value||undefined}))
function scrollEnd(){if(following.value)void nextTick(()=>host.value?.scrollTo({top:host.value.scrollHeight,behavior:'smooth'}))}
async function read(reset=false,tail=false){
  if(!selected.value||loading.value)return
  const stamp=sequence
  loading.value=true;error.value=''
  try{
    const response=await logApi.page(selected.value,{...filters.value,cursor:reset?null:cursor.value,limit:200,tail_mode:tail})
    if(stamp!==sequence)return
    if(reset)events.value=response.events
    else events.value=events.value.concat(response.events).slice(-2000)
    cursor.value=response.next_cursor
    if(tail)tailMode.value=true
    scrollEnd()
  }catch(e){if(stamp===sequence)error.value=errorText(e)}
  finally{loading.value=false}
}
function reset(tail=true){
  sequence++;events.value=[];cursor.value=null;tailMode.value=tail
  void read(true,tail)
}
onMounted(async()=>{
  try{
    const data=await runApi.list(200);runs.value=data.runs
    const requested=typeof route.query.run==='string'?route.query.run:''
    selected.value=data.runs.some(r=>r.id===requested)?requested:data.runs[0]?.id||''
    reset()
  }catch(e){error.value=errorText(e)}
})
watch([selected,level,source],()=>reset())
watch(search,()=>{if(searchTimer)clearTimeout(searchTimer);searchTimer=setTimeout(()=>reset(),400)})
usePolling(async()=>{
  if(!selected.value||!tailMode.value||loading.value||!following.value)return
  const last=events.value.at(-1)?.at
  await read(false,false)
  if(events.value.at(-1)?.at!==last)scrollEnd()
},3500)
function copied(){
  const rows=events.value.map(e=>[e.at,e.level,e.source||e.model||'API',e.message].join(' | ')).join('\n')
  void navigator.clipboard.writeText(rows).then(()=>notice.add('Загруженные строки скопированы','ok')).catch(e=>error.value=errorText(e))
}
async function download(){
  if(!selected.value)return
  try{
    let next:string|null=null
    const lines:string[]=[]
    do{
      const chunk=await logApi.page(selected.value,{...filters.value,cursor:next,limit:500,tail:false})
      for(const e of chunk.events)lines.push(JSON.stringify(e))
      next=chunk.next_cursor
      if(lines.length>120000)throw new Error('Журнал слишком большой для браузера. Сузьте фильтр.')
    }while(next)
    const url=URL.createObjectURL(new Blob([lines.join('\n')+'\n'],{type:'application/x-ndjson;charset=utf-8'}))
    const a=document.createElement('a');a.href=url;a.download='photosorter-'+selected.value+'-events.jsonl';a.click()
    setTimeout(()=>URL.revokeObjectURL(url),1500)
  }catch(e){error.value=errorText(e)}
}
function scrolled(){
  if(!host.value)return
  const el=host.value
  if(el.scrollHeight-el.scrollTop-el.clientHeight>90)following.value=false
}
</script>
<template>
<PageHeader eyebrow="ДИАГНОСТИКА" title="Логи" subtitle="Журнал запусков с поиском, уровнями, источниками и подгрузкой.">
  <template #actions><UiButton @click="copied" :disabled="!events.length">Скопировать</UiButton><UiButton @click="download" :disabled="!selected">↓ Скачать журнал</UiButton></template>
</PageHeader>
<div class="panel stack" style="margin-bottom:18px">
  <div class="grid3">
    <label class="field"><span class="label">Запуск</span><select v-model="selected"><option v-for="run in runs" :key="run.id" :value="run.id">{{date(run.started_at)}} · {{run.id}}</option></select></label>
    <label class="field"><span class="label">Уровень</span><select v-model="level"><option value="">Все</option><option>INFO</option><option>WARNING</option><option>ERROR</option></select></label>
    <label class="field"><span class="label">Источник</span><select v-model="source"><option value="">Все</option><option value="API">API</option><option value="MegaLoc">MegaLoc</option></select></label>
  </div>
  <div class="row between wrap"><input v-model="search" placeholder="Поиск по сообщениям…" aria-label="Поиск логов" style="max-width:390px"/><label class="row meta"><input v-model="following" type="checkbox"/>Автопрокрутка</label></div>
</div>
<div v-if="error" class="alert error" role="alert" style="margin-bottom:14px">{{error}}</div>
<div v-if="selected" class="panel stack">
  <div class="row between wrap"><span class="meta">{{events.length}} загруженных событий · отображение не более 2000 строк</span>
    <div class="row"><UiButton small @click="reset(!tailMode)">{{tailMode?'История с начала':'Перейти к новым'}}</UiButton><UiButton v-if="!following" small @click="following=true;scrollEnd()">В конец ↓</UiButton></div>
  </div>
  <div ref="host" style="max-height:65vh;min-height:230px;overflow:auto;border:1px solid var(--border);border-radius:10px;background:var(--input)" @scroll.passive="scrolled">
    <div v-for="(event,index) in events" :key="event.at+'-'+index" class="row" style="align-items:flex-start;gap:15px;padding:10px 14px;border-bottom:1px solid var(--border-subtle)">
      <time class="meta" style="flex:0 0 145px">{{date(event.at)}}</time>
      <span class="status" :class="event.level==='ERROR'?'danger':event.level==='INFO'?'ok':''">{{event.level}}</span>
      <span class="meta" style="flex:0 0 72px">{{event.source||event.model||'API'}}</span>
      <span style="min-width:0;overflow-wrap:anywhere;white-space:pre-wrap">{{event.message}}</span>
    </div>
    <div v-if="!events.length&&!loading" class="meta" style="padding:24px">Журнал пуст для выбранных фильтров.</div>
  </div>
  <div v-if="cursor&&!tailMode" class="pagination"><UiButton :loading="loading" @click="read(false,false)">Показать следующую страницу</UiButton></div>
</div>
<EmptyState v-else title="Запусков пока нет" detail="После первой обработки здесь появятся события MegaLoc." icon="⌘"/>
</template>
