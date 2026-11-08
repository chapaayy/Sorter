<script setup lang="ts">
import {onMounted,ref,computed} from 'vue'
import {adPipelineApi} from '../../api/adPipeline'
import type {BestSummary,BestPhoto} from '../../api/adPipeline'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import {errorText} from '../../utils/format'

const props=defineProps<{runId:string}>()
const emit=defineEmits<{(e:'open',index:number):void}>()
const summary=ref<BestSummary|null>(null),error=ref(''),loading=ref(true)
const selected=ref('')

const completed=computed(()=>{
  // Saved historical results can contain one winner per T subgroup. Display
  // only one per construction+layout here as a backwards-compatible view.
  const unique=new Map<string,BestPhoto>()
  for(const item of summary.value?.best||[]){
    if(!item.candidate_id||!item.assigned_sam)continue
    const key=item.assigned_sam+'|'+item.candidate_id
    const previous=unique.get(key)
    const rank=(value:BestPhoto)=>value.selection_score??
      ((value.quality?.score??0)/2+(value.ocr?.text_similarity??0)*50)
    if(!previous||rank(item)>rank(previous)||
        (rank(item)===rank(previous)&&item.index<previous.index)){
      unique.set(key,item)
    }
  }
  return [...unique.values()].sort((a,b)=>a.assigned_sam.localeCompare(b.assigned_sam,'ru',{numeric:true})||
    a.layout_name.localeCompare(b.layout_name,'ru',{numeric:true}))
})
const folders=computed(()=>[...new Set(completed.value.map(item=>item.assigned_sam))])
const photos=computed(()=>completed.value.filter(item=>item.assigned_sam===selected.value))
onMounted(async()=>{
  try{
    summary.value=await adPipelineApi.best(props.runId)
    selected.value=folders.value[0]||''
  }catch(e){error.value=errorText(e)}
  finally{loading.value=false}
})
function photoUrl(index:number){
  return '/api/images/'+encodeURIComponent(props.runId)+'/megaloc/'+index+'?kind=query'
}
</script>
<template>
<section class="stack result-ad-view result-final-view">
  <div class="row between wrap">
    <div>
      <h2>Готовые фотографии рекламы</h2>
      <p class="meta">По одной лучшей ФО на конструкцию и макет. Остальные кадры и диагностические группы остаются в других вкладках.</p>
    </div>
    <span v-if="summary?.status==='completed'" class="meta">
      {{folders.length}} конструкций · {{completed.length}} готовых фото
    </span>
  </div>
  <p class="meta">В полном ZIP: <strong>Best_by_layout / Конструкция / Название макета / ФО</strong></p>
  <div v-if="error" class="alert error">{{error}}</div>
  <EmptyState v-else-if="!loading&&!completed.length" title="Готовых рекламных фото нет"
    detail="Для этого запуска нет сопоставленных рекламных макетов либо обработка ещё не завершена."/>
  <div v-else-if="folders.length" class="result-final-layout">
    <aside class="panel stack result-final-folders">
      <strong>Конструкции</strong>
      <button v-for="sam in folders" :key="sam" type="button"
        :class="['result-final-folder',{active:selected===sam}]"
        :aria-pressed="selected===sam" @click="selected=sam">
        <span>{{sam}}</span>
        <span class="meta">{{completed.filter(photo=>photo.assigned_sam===sam).length}}</span>
      </button>
    </aside>
    <section class="panel stack">
      <div class="row between wrap">
        <h2>{{selected}}</h2>
        <span class="meta">{{photos.length}} макетов · {{photos.length}} готовых фото</span>
      </div>
      <div class="result-final-grid">
        <article v-for="item in photos" :key="item.candidate_id" class="result-final-card">
          <img :src="photoUrl(item.index)" :alt="'ФО '+(item.index+1)+' · '+item.layout_name" loading="lazy"/>
          <div class="stack-sm">
            <strong>{{item.layout_name}}</strong>
            <span class="meta">{{selected}} / {{item.layout_name}}</span>
            <span class="meta">Лучшее ФО №{{item.index+1}}
              <span v-if="item.screen_name"> · {{item.screen_name}}</span></span>
            <span class="meta">Качество: {{item.quality.score.toFixed(1)}} / 100</span>
            <span v-if="item.ocr?.total_terms" class="meta">
              OCR: {{item.ocr.matched_terms??0}} из {{item.ocr.total_terms}} слов ФО
            </span>
            <span v-else class="meta">OCR: текст не прочитан · выбор по DINOv2 и качеству</span>
            <strong v-if="item.selection_score!=null" class="result-final-score">
              Итоговый балл: {{item.selection_score.toFixed(1)}} / 100
            </strong>
            <UiButton small @click="emit('open',item.index)">Открыть оригинал</UiButton>
          </div>
        </article>
      </div>
    </section>
  </div>
</section>
</template>
