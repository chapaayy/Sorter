<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {adPipelineApi} from '../../api/adPipeline'
import type {BestSummary,BestPhoto} from '../../api/adPipeline'
import UiButton from '../../components/ui/UiButton.vue'
import {errorText} from '../../utils/format'

const props=defineProps<{runId:string}>()
const emit=defineEmits<{(e:'open',index:number):void}>()
const summary=ref<BestSummary|null>(null),error=ref('')
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
        <p class="meta">DINOv2 сопоставляет рекламу с макетом. Лучший кадр определяется средним баллом совпавших слов OCR и качества экрана.</p>
      </div>
      <RouterLink class="meta" to="/layouts">Библиотека рекламы</RouterLink>
    </div>
    <div v-if="error" class="alert error">{{error}}</div>
    <template v-else-if="summary">
      <p v-if="summary.status==='not_processed'" class="meta">Обработка рекламы ещё не завершена.</p>
      <template v-else>
        <div class="row wrap ad-best-stats">
          <span>Найдено экранов: <strong>{{summary.screens_found??0}}</strong></span>
          <span>Распознано: <strong>{{summary.recognized??0}}</strong></span>
          <span>Лучших кадров: <strong>{{summary.best.length}}</strong></span>
          <span v-if="summary.text_subgroup_count!=null">Вариантов текста: <strong>{{summary.text_subgroup_count}}</strong></span>
          <span v-if="summary.errors" class="meta">Ошибки ФО: {{summary.errors}}</span>
        </div>
        <p v-if="!summary.best.length" class="meta">
          Визуальных совпадений DINOv2 нет. Оригинальные ФО остаются в ZIP.
        </p>
        <template v-else>
          <strong>Выбранные лучшие фотографии</strong>
          <p class="meta">Если OCR не прочитал ни слова, кадр оценивается по качеству экрана. Отсутствие текста не требует ручной проверки.</p>
          <div class="ad-best-grid">
            <article v-for="item in summary.best" :key="item.screen_id+':'+item.candidate_id+':'+item.text_subgroup_id+':'+item.index"
              class="ad-best-item">
              <img :src="'/api/images/'+encodeURIComponent(runId)+'/megaloc/'+item.index+'?kind=query'"
                :alt="'Лучшая ФО №'+(item.index+1)" loading="lazy"/>
              <div class="stack-sm">
                <strong>{{item.layout_name}}</strong>
                <span class="meta">{{item.assigned_sam}} · {{item.screen_name||'Экран'}}
                  <span v-if="item.text_subgroup_id"> · {{item.text_subgroup_id}}</span></span>
                <span class="meta">ФО №{{item.index+1}} · Качество: {{item.quality.score.toFixed(1)}} / 100</span>
                <span v-if="item.ocr?.total_terms" class="meta">
                  OCR: {{item.ocr.matched_terms??0}} из {{item.ocr.total_terms}} прочитанных элементов
                </span>
                <span v-else class="meta">OCR: текст не прочитан · визуальное сопоставление DINOv2</span>
                <span v-if="item.selection_score!=null" class="meta">
                  Итог: {{item.selection_score.toFixed(1)}} / 100
                  · OCR-балл: {{(item.ocr_selection_score??0).toFixed(1)}}
                  · Качество: {{item.quality.score.toFixed(1)}}
                </span>
                <UiButton small @click="focus(item)">Открыть ФО</UiButton>
              </div>
            </article>
          </div>
        </template>
      </template>
    </template>
  </section>
</template>
