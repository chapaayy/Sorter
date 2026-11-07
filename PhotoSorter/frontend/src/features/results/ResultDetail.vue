<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {batchApi} from '../../api/batches'
import {resultApi} from '../../api/results'
import {referenceApi} from '../../api/references'
import {useCursor} from '../../composables/useCursor'
import type {Batch,Run,ResultPhoto,Retention} from '../../types/api'
import {bytes,date,errorText,friendlySam,isComplete} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
import GroupPicker from '../../components/split/GroupPicker.vue'
import VirtualThumbnailGrid from '../../components/gallery/VirtualThumbnailGrid.vue'
import ImageViewer from '../../components/gallery/ImageViewer.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import {useNoticeStore} from '../../stores/notice'
const route=useRoute(),router=useRouter(),id=String(route.params.runId),notice=useNoticeStore()
const run=ref<Run|null>(null),batch=ref<Batch|null>(null),retention=ref<Retention|null>(null)
const sams=ref<Record<string,number>>({}),groups=ref<Record<string,number>>({}),referenceNames=ref<Record<string,string>>({}),mode=ref<'sam'|'group'>('sam')
const selected=ref(''),lastSam=ref(''),lastGroup=ref(''),error=ref(''),busy=ref(false)
const viewer=ref<number|null>(null),deleteWhole=ref(false)
const displaySam=(sam:string)=>referenceNames.value[sam]||friendlySam(sam)
const list=computed(()=>Object.entries(mode.value==='sam'?sams.value:groups.value)
  .sort(([a],[b])=>a==='_Неопределено'?1:b==='_Неопределено'?-1:a.localeCompare(b,'ru',{numeric:true}))
  .map(([key,count])=>({id:key,label:mode.value==='sam'?displaySam(key):key,count})))
const {items,cursor,loading,error:pageError,load,reset}=useCursor<ResultPhoto>(next=>
  resultApi.photos(id,{[mode.value==='sam'?'sam':'group']:selected.value,cursor:next,limit:60}))
const tiles=computed(()=>items.value.map(p=>({id:String(p.index),label:'ФО №'+(p.index+1),thumbnail_url:p.thumbnail_url,original_url:p.image_url,score:p.score})))
const previews=computed(()=>items.value.map(p=>({src:p.image_url,label:'ФО №'+(p.index+1)+' · '+displaySam(p.assigned_sam||''),score:p.score})))
const total=computed(()=>Object.values(sams.value).reduce((x,y)=>x+y,0))
function changeMode(value:'sam'|'group'){
  if(mode.value===value)return
  if(mode.value==='sam')lastSam.value=selected.value;else lastGroup.value=selected.value
  mode.value=value
  selected.value=(value==='sam'?lastSam.value:lastGroup.value)||list.value[0]?.id||''
}
watch(selected,(value,old)=>{if(value!==old&&value)void reset()})
onMounted(async()=>{
  try{
    run.value=await resultApi.one(id)
    if(!isComplete(run.value.status)){error.value='Этот запуск ещё не завершён';return}
    const [b,s,g,refs]=await Promise.all([batchApi.one(run.value.batch_id),resultApi.sam(id),resultApi.groups(id),referenceApi.list().catch(()=>null)])
    referenceNames.value=Object.fromEntries((refs?.sam||[]).map(item=>[item.sam,item.display_name||item.sam]))
    batch.value=b;sams.value=s;groups.value=g;selected.value=list.value[0]?.id||''
    retention.value=await batchApi.retention(b.batch_id)
  }catch(e){error.value=errorText(e)}
})
function download(sam?:string){
  const anchor=document.createElement('a')
  anchor.href=resultApi.download(id,sam)
  anchor.download='photosorter-'+id+'.zip'
  document.body.append(anchor)
  anchor.click();anchor.remove()
}
async function extend(){
  if(!batch.value)return
  busy.value=true
  try{retention.value=await batchApi.extend(batch.value.batch_id);notice.add('Срок хранения продлён','ok')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function deleteBatch(){
  if(!batch.value)return
  busy.value=true
  try{await batchApi.remove(batch.value.batch_id);deleteWhole.value=false;notice.add('Партия поставлена на полное удаление','ok');await router.push('/results')}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="row" style="margin-bottom:22px"><RouterLink class="meta" to="/results">← Все результаты</RouterLink></div>
<PageHeader eyebrow="РЕЗУЛЬТАТЫ / MEGALOC" :title="batch?.display_name||'Результат запуска'" :subtitle="total+' ФО · '+Object.keys(groups).length+' групп ФО · '+date(run?.started_at)">
  <template #actions><UiButton kind="primary" :disabled="!run||!isComplete(run.status)" @click="download()">↓ Скачать всю сортировку ZIP</UiButton><UiButton kind="danger" :disabled="!batch" @click="deleteWhole=true">Удалить всю партию</UiButton></template>
</PageHeader>
<div v-if="error" class="alert error" role="alert" style="margin-bottom:18px">{{error}}</div>
<section v-if="batch&&run" class="panel stack" style="margin-bottom:18px">
  <div class="row between wrap">
    <div><strong>Готовый ZIP</strong>
      <p class="meta" style="margin:4px 0">Архив подготовлен автоматически после сортировки.</p>
    </div>
    <span v-if="retention?.delete_after_at" class="meta">
      Автоудаление: <strong>{{date(retention.delete_after_at)}}</strong>
    </span>
    <span v-else class="meta">Для этой партии автоматическое удаление не назначено.</span>
  </div>
  <div v-if="retention?.delete_after_at" class="row between wrap">
    <span class="meta">При удалении партии архив и фотографии удалятся вместе.</span>
    <UiButton small :loading="busy" @click="extend">Продлить хранение</UiButton>
  </div>
  <div v-if="retention?.warning" class="alert warning">До автоматического удаления осталось менее 7 дней.</div>
</section>
<div class="row wrap between" style="margin-bottom:16px">
  <div class="segment" role="tablist" aria-label="Способ группировки">
    <button role="tab" :aria-selected="mode==='sam'" @click="changeMode('sam')">По конструкциям</button>
    <button role="tab" :aria-selected="mode==='group'" @click="changeMode('group')">По группам ФО</button>
  </div>
  <span class="meta">Оценки показаны только для отдельных ФО, из manifest MegaLoc.</span>
</div>
<div v-if="list.length" class="split">
  <GroupPicker v-model="selected" :items="list" :placeholder="mode==='sam'?'Поиск номера или адреса…':'Поиск группы…'"/>
  <section class="panel split-main">
    <div class="panel-header">
      <div><h2>{{mode==='sam'?displaySam(selected):selected}}</h2><span class="meta">{{list.find(x=>x.id===selected)?.count||0}} ФО</span></div>
      <UiButton v-if="mode==='sam'" small @click="download(selected)">↓ Скачать конструкцию</UiButton>
    </div>
    <div v-if="pageError" class="alert error" role="alert">{{pageError}}</div>
    <VirtualThumbnailGrid v-if="items.length" :items="tiles" :show-scores="true" @open="i=>viewer=i"/>
    <EmptyState v-else-if="!loading" title="Фотографий здесь нет" detail="Выберите другую SAM или группу."/>
    <div v-if="cursor" class="pagination"><UiButton :loading="loading" @click="load()">Показать ещё</UiButton></div>
  </section>
</div>
<EmptyState v-else-if="run" title="Результаты ещё не опубликованы" detail="Проверьте статус обработки и журнал запуска."/>
<ImageViewer v-if="viewer!==null" :items="previews" :initial="viewer" @close="viewer=null"/>
<ConfirmDialog v-if="deleteWhole&&batch" title="Удалить ВСЮ партию безвозвратно?" :message="'Удалятся оригинальные ФО, все запуски, готовые результаты, миниатюры, временные файлы и логи партии «'+batch.display_name+'». Общая библиотека SAM останется.'" :required-text="batch.display_name" danger confirm-label="Удалить всю партию" :busy="busy" @confirm="deleteBatch" @cancel="deleteWhole=false"/>
</template>
