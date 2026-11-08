<script setup lang="ts">
import {onMounted,ref,computed} from 'vue'
import {usePolling} from '../../composables/usePolling'
import {adLayoutApi} from '../../api/adLayouts'
import {adPipelineApi} from '../../api/adPipeline'
import type {AdLayout} from '../../api/adLayouts'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import {errorText} from '../../utils/format'
import {useNoticeStore} from '../../stores/notice'

const notice=useNoticeStore()
const layouts=ref<AdLayout[]>([]),selected=ref<File|null>(null),name=ref(''),expected=ref('')
const busy=ref(false),error=ref(''),editing=ref<AdLayout|null>(null)
const editName=ref(''),editText=ref(''),editActive=ref(true)
const activeCount=computed(()=>layouts.value.filter(item=>item.active).length)
const pipeline=ref(false),pipelineBusy=ref(false),pipelineReady=ref(false)
async function loadPipeline(){
  try{const status=await adPipelineApi.settings();pipeline.value=status.enabled;pipelineReady.value=true}
  catch(e){error.value=errorText(e)}
}
async function changePipeline(){
  if(pipelineBusy.value)return
  pipelineBusy.value=true
  try{
    const status=await adPipelineApi.update(pipeline.value)
    pipeline.value=status.enabled
    notice.add(pipeline.value?'Обработка рекламы включена для новых заданий':
      'Обработка рекламы отключена для новых заданий','ok')
  }catch(e){
    pipeline.value=!pipeline.value
    error.value=errorText(e)
  }finally{pipelineBusy.value=false}
}
async function refresh(){
 try{layouts.value=(await adLayoutApi.list()).layouts;error.value=''}
 catch(e){error.value=errorText(e)}
}
function choose(event:Event){
 const file=(event.target as HTMLInputElement).files?.[0]||null
 selected.value=file
 if(file)name.value=file.name.replace(/\.[^.]+$/,'').slice(0,120)
}
async function upload(){
 if(!selected.value||!name.value.trim()||busy.value)return
 busy.value=true;error.value=''
 try{
  await adLayoutApi.upload(selected.value,name.value.trim(),expected.value.trim())
  selected.value=null;name.value='';expected.value=''
  const picker=document.querySelector<HTMLInputElement>('#ad-layout-file')
  if(picker)picker.value=''
  notice.add('Макет поставлен в общую очередь на подготовку','ok');await refresh()
 }catch(e){error.value=errorText(e)}
 finally{busy.value=false}
}
function edit(item:AdLayout){
 editing.value=item
 editName.value=item.name;editText.value=item.corrected_text??item.expected_text;editActive.value=item.active
}
async function save(){
 if(!editing.value||busy.value)return
 busy.value=true;error.value=''
 try{
  await adLayoutApi.edit(editing.value,editName.value.trim(),editText.value.trim(),editActive.value)
  editing.value=null;notice.add('Параметры макета обновлены','ok');await refresh()
 }catch(e){error.value=errorText(e)}
 finally{busy.value=false}
}
async function replaceImage(item:AdLayout,event:Event){
 const input=event.target as HTMLInputElement
 const file=input.files?.[0]
 if(!file||busy.value)return
 busy.value=true;error.value=''
 try{
   await adLayoutApi.replaceImage(item,file)
   notice.add('Новая версия изображения поставлена в очередь','ok')
   await refresh()
 }catch(e){error.value=errorText(e)}
 finally{busy.value=false;input.value=''}
}
async function remove(item:AdLayout){
 if(busy.value||!window.confirm('Удалить макет «'+item.name+'»? Старые результаты анализа останутся в истории до удаления партии.'))return
 busy.value=true;error.value=''
 try{await adLayoutApi.remove(item.id);notice.add('Макет удалён','ok');await refresh()}
 catch(e){error.value=errorText(e)}finally{busy.value=false}
}
onMounted(()=>{void refresh();void loadPipeline()})
usePolling(refresh,4000)
</script>
<template>
 <PageHeader eyebrow="БИБЛИОТЕКА РЕКЛАМЫ" title="Макеты рекламы"
   subtitle="Эталоны рекламного изображения для DINOv2. Не смешиваются с Образцами конструкций."/>
 <div v-if="error" class="alert error" role="alert">{{error}}</div>
 <section class="panel stack ad-layout-upload">
   <div class="row between wrap">
     <div><h2>Распознавание рекламы в общей очереди</h2>
       <p class="meta">Новые ФО: MegaLoc → XFeat → DINOv2 → OCR → качество → ZIP.
         Ранее поставленные задания не меняются.</p>
       <p class="meta">Для включения нужны XFeat, DINOv2, PP-OCRv5
         и подготовленные активные макеты. Подготовка выполняется в общей очереди.</p>
     </div>
     <label class="row wrap" style="gap:10px">
       <input v-model="pipeline" type="checkbox" aria-label="Распознавать рекламу при обработке ФО"
         :disabled="!pipelineReady||pipelineBusy" @change="changePipeline"/>
       <strong>{{pipeline?'Включено':'Выключено'}}</strong>
     </label>
   </div>
 </section>
 <section class="panel stack ad-layout-upload">
   <div><h2>Добавить рекламный макет</h2>
   <p class="meta">JPG, PNG или WEBP до 20 МиБ. Оригинал сохраняется без изменения.</p></div>
   <form class="ad-layout-upload-form" @submit.prevent="upload">
    <label class="field">Изображение макета
     <input id="ad-layout-file" type="file" accept="image/png,image/jpeg,image/webp"
       aria-label="Изображение рекламного макета" @change="choose"/>
    </label>
    <label class="field">Название
     <input v-model="name" maxlength="120" required placeholder="Название рекламной кампании"/>
    </label>
    <label class="field">Исправленный текст макета (необязательно)
     <input v-model="expected" maxlength="1000" placeholder="Например, СКИДКИ 50%">
    </label>
    <UiButton kind="primary" type="submit" :disabled="!selected||!name.trim()" :loading="busy">
      + Добавить макет
    </UiButton>
   </form>
   <p class="meta">После загрузки DINOv2 и PaddleOCR подготовят макет в общей очереди.
      При пустом исправленном тексте используется результат OCR исходного макета.</p>
 </section>
 <div class="row between wrap ad-layout-count">
  <span class="meta">Всего {{layouts.length}} макетов · {{activeCount}} активных</span>
  <RouterLink class="meta" to="/results">Перейти к результатам ФО</RouterLink>
 </div>
 <div v-if="layouts.length" class="ad-layout-list">
  <article v-for="item in layouts" :key="item.id" class="panel ad-layout-item">
   <img :src="item.image_url" :alt="item.name" loading="lazy"/>
   <div class="stack-sm">
    <div class="row wrap"><strong>{{item.name}}</strong>
     <span class="status">{{item.active?'Активен':'Отключён'}}</span>
     <span class="status" :class="item.preparation_state==='completed'?'ok':item.preparation_state==='failed'?'danger':''">
       {{item.preparation_state==='completed'?'Подготовлен':
         item.preparation_state==='running'?'Подготовка':
         item.preparation_state==='failed'?'Ошибка подготовки':'В очереди'}}
     </span></div>
    <div v-if="item.preparation_state==='running'" class="meta" role="status">
      {{item.preparation_stage}} · {{item.preparation_progress}}%
      <progress :value="item.preparation_progress" max="100" style="width:100%"/>
    </div>
    <div v-if="item.preparation_error" class="meta" style="color:var(--danger)">
      {{item.preparation_error}}</div>
    <div class="meta">Текст для сверки: {{(item.corrected_text??item.expected_text)||item.ocr_normalized_text||'Не распознан'}}</div>
    <details v-if="item.ocr_raw_lines.length">
      <summary class="meta">Распознанный текст и уверенность OCR</summary>
      <div v-for="(line,index) in item.ocr_raw_lines" :key="index" class="meta">
        {{line.text}} · {{line.score.toFixed(2)}}
      </div>
    </details>
    <div class="meta">Версия {{item.version}} · {{(item.byte_size/1048576).toFixed(2)}} МиБ</div>
    <div class="row wrap">
     <UiButton small @click="edit(item)">Изменить</UiButton>
     <UiButton small kind="danger" :disabled="busy" @click="remove(item)">Удалить</UiButton>
    </div>
    <label class="field meta">Заменить изображение макета
      <input type="file" accept="image/png,image/jpeg,image/webp" :disabled="busy"
        :aria-label="'Заменить изображение '+item.name" @change="replaceImage(item,$event)"/>
    </label>
   </div>
  </article>
 </div>
 <EmptyState v-else title="Макетов пока нет"
   detail="Добавьте исходные рекламные изображения, которые будут сравниваться с экранами на ФО."/>
 <div v-if="editing" class="modal-overlay" @click.self="editing=null">
  <form class="modal stack" role="dialog" aria-modal="true" aria-label="Изменить макет"
    @submit.prevent="save">
    <h2>Изменить макет</h2>
    <label class="field">Название<input v-model="editName" maxlength="120" required/></label>
    <label class="field">Исправленный текст для сверки
      <textarea v-model="editText" maxlength="1000" rows="3" placeholder="Пусто — использовать OCR автоматически"/>
    </label>
    <p class="meta">Распознано: {{editing.ocr_normalized_text||'Текст ещё не подготовлен'}}</p>
    <label class="row wrap"><input v-model="editActive" type="checkbox"/> Использовать для распознавания</label>
    <div class="modal-actions"><UiButton @click="editing=null">Отмена</UiButton>
     <UiButton kind="primary" type="submit" :loading="busy">Сохранить</UiButton></div>
  </form>
 </div>
</template>
