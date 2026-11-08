<script setup lang="ts">
import {onMounted,ref,computed} from 'vue'
import {adPipelineApi} from '../../api/adPipeline'
import type {BestSummary,BestPhoto} from '../../api/adPipeline'
import UiButton from '../../components/ui/UiButton.vue'
import {errorText} from '../../utils/format'
const props=defineProps<{runId:string}>()
const emit=defineEmits<{(e:'open',index:number):void}>()
const summary=ref<BestSummary|null>(null),error=ref('')
const confirmed=computed(()=>summary.value?.best.filter(item=>!item.review_required)||[])
const review=computed(()=>summary.value?.best.filter(item=>item.review_required)||[])
onMounted(async()=>{
  try{summary.value=await adPipelineApi.best(props.runId)}
  catch(e){error.value=errorText(e)}
})
function focus(item:BestPhoto){emit('open',item.index)}
</script>
<template>
  <section class="panel stack ad-best-panel">
    <div class="row between wrap">
      <div>
        <h2>Лучшие кадры по рекламным макетам</h2>
        <p class="meta">DINOv2 определяет макет, PP-OCRv5 проверяет текст. Качество оценивается только на найденном экране.</p>
      </div>
      <RouterLink class="meta" to="/layouts">Библиотека рекламы</RouterLink>
    </div>
    <div v-if="error" class="alert error">{{error}}</div>
    <template v-else-if="summary">
      <div v-if="summary.status==='not_processed'" class="meta">
        Обработка рекламы ещё не завершена.
      </div>
      <template v-else>
        <div class="row wrap ad-best-stats">
          <span>Найдено экранов: <strong>{{summary.screens_found??0}}</strong></span>
          <span>Распознано: <strong>{{summary.recognized??0}}</strong></span>
          <span>Лучших кадров: <strong>{{summary.best.length}}</strong></span>
          <span v-if="summary.errors" class="meta">Ошибки ФО: {{summary.errors}}</span>
        </div>
        <p v-if="!summary.best.length" class="meta">
          Надёжных совпадений нет. Исходные ФО остаются в ZIP;
          проверьте разметки экранов и библиотеку макетов.
        </p>
        <template v-if="confirmed.length">
          <strong>Подтверждённые</strong>
          <div class="ad-best-grid">
            <article v-for="item in confirmed" :key="item.screen_id+':'+item.candidate_id"
              class="ad-best-item">
              <img :src="'/api/images/'+encodeURIComponent(runId)+'/megaloc/'+item.index+'?kind=query'"
                :alt="'Лучшая ФО №'+(item.index+1)" loading="lazy"/>
              <div class="stack-sm">
                <strong>{{item.layout_name}}</strong>
                <span class="meta">{{item.assigned_sam}} · {{item.screen_name||'Экран'}}</span>
                <span class="meta">Качество: {{item.quality.score.toFixed(1)}} / 100 · ФО №{{item.index+1}}</span>
                <UiButton small @click="focus(item)">Открыть ФО</UiButton>
              </div>
            </article>
          </div>
        </template>
        <template v-if="review.length">
          <strong>Требуется проверка</strong>
          <p class="meta">Эти лучшие по качеству кадры в ZIP находятся отдельно от подтверждённых.</p>
          <div class="ad-best-grid">
            <article v-for="item in review" :key="item.screen_id+':'+item.candidate_id"
              class="ad-best-item">
              <img :src="'/api/images/'+encodeURIComponent(runId)+'/megaloc/'+item.index+'?kind=query'"
                :alt="'ФО для проверки №'+(item.index+1)" loading="lazy"/>
              <div class="stack-sm">
                <strong>{{item.layout_name}}</strong>
                <span class="meta">{{item.assigned_sam}} · {{item.screen_name||'Экран'}}</span>
                <span class="meta">Качество: {{item.quality.score.toFixed(1)}} / 100 · ФО №{{item.index+1}}</span>
                <span class="meta">{{item.ocr?.reason||'Необходима проверка рекламы'}}</span>
                <UiButton small @click="focus(item)">Открыть ФО</UiButton>
              </div>
            </article>
          </div>
        </template>
      </template>
    </template>
  </section>
</template>
