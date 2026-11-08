<script setup lang="ts">
import {computed} from 'vue'
import type {OcrRecognition} from '../../api/adResults'

const props=defineProps<{recognition:OcrRecognition}>()
type Word={text:string;kind:'same'|'different'|'space'}
function segments(text:string,other:string):Word[]{
  const words=new Set((other.toLowerCase().match(/[a-zа-яё0-9]+/gi)||[]))
  return (text.match(/[a-zа-яё0-9]+|[^a-zа-яё0-9]+/gi)||[]).map(token=>({
    text:token,
    kind:!/[a-zа-яё0-9]/i.test(token)?'space':words.has(token.toLowerCase())?'same':'different'
  }))
}
const prepared=computed(()=>props.recognition.ocr?.expected_text||
  props.recognition.layout_text||'')
const actual=computed(()=>props.recognition.observation?.normalized_text||
  props.recognition.ocr?.lines?.join(' ')||'')
const layoutSegments=computed(()=>segments(prepared.value,actual.value))
const observedSegments=computed(()=>segments(actual.value,prepared.value))
const issues=computed(()=>props.recognition.ocr?.contradictions||[])
const labels:Record<string,string>={dates:'Даты',prices:'Цены',percentages:'Проценты',numbers:'Числа'}
const statLabel=(status?:string)=>({
  confirmed:'Подтверждено',mismatch:'Противоречие',
  probable:'Недостаточно данных',unreadable:'Не прочитано',
  not_configured:'Текст макета не задан',unavailable:'OCR недоступен',
  error:'Ошибка OCR',not_run:'Не проверено',not_processed:'Нет результата'
} as Record<string,string>)[status||'']||status||'Нет результата'
</script>
<template>
<div class="stack-sm result-ocr-evidence">
  <div class="row between wrap">
    <strong>PP-OCRv5 · {{statLabel(recognition.ocr?.status)}}</strong>
    <span class="meta">Уверенность OCR: {{recognition.observation?.confidence==null?'—':
      recognition.observation.confidence.toFixed(3)}} · {{recognition.classification||'не определено'}}</span>
  </div>
  <p class="meta">{{recognition.ocr?.reason||recognition.reason||'Нет текстовых данных'}}</p>
  <p v-if="recognition.ocr?.scoring_basis==='recognized_photo_text'" class="meta">
    Совпало {{recognition.ocr.matched_terms??0}} из {{recognition.ocr.total_terms??0}}
    достоверно прочитанных элементов ФО
    <span v-if="recognition.ocr.text_similarity!=null">
      · {{(recognition.ocr.text_similarity*100).toFixed(0)}}%
    </span>
  </p>
  <p v-if="recognition.ocr?.unmatched_items?.length" class="meta">
    Не найдены в макете: {{recognition.ocr.unmatched_items.join(' · ')}}
  </p>
  <p v-if="recognition.ocr?.ambiguous_candidates?.length" class="meta">
    Текст также подходит другим визуально совместимым макетам:
    {{recognition.ocr.ambiguous_candidates.length}}
  </p>
  <div class="result-ocr-columns">
    <div><strong>Подготовленный текст макета</strong>
      <p v-if="prepared" class="result-ocr-words"><span v-for="(word,i) in layoutSegments" :key="i"
        :class="'result-ocr-'+word.kind">{{word.text}}</span></p>
      <p v-else class="meta">Нет привязанного / подготовленного текста</p>
    </div>
    <div><strong>Прочитано с экрана</strong>
      <p v-if="actual" class="result-ocr-words"><span v-for="(word,i) in observedSegments" :key="i"
        :class="'result-ocr-'+word.kind">{{word.text}}</span></p>
      <p v-else class="meta">Не удалось достоверно прочитать текст</p>
    </div>
  </div>
  <p v-if="recognition.ocr?.possible_contradictions?.length&&!issues.length" class="meta">
    Возможное несовпадение дат или чисел, но OCR недостаточно уверен:
    {{recognition.ocr.possible_contradictions.map(item=>item.kind+': '+item.observed.join(', ')).join(' · ')}}
  </p>
  <div v-for="(issue,i) in issues" :key="i" class="result-ocr-conflict">
    <strong>{{labels[issue.kind]||issue.kind}} · несоответствие</strong>
    <span>Макет: {{issue.expected.join(', ')||'—'}}</span>
    <span>На экране: {{issue.observed.join(', ')||'—'}}</span>
  </div>
  <div v-if="recognition.observation?.raw_lines?.length" class="result-ocr-lines">
    <div v-for="(line,i) in recognition.observation.raw_lines" :key="i" class="row between">
      <span>{{line.text}}</span>
      <span class="meta">{{line.score.toFixed(3)}} · {{line.polygon?'есть координаты':'без координат'}}</span>
    </div>
  </div>
  <span v-if="recognition.visual_group_id||recognition.text_subgroup_id" class="meta">
    Визуальная группа {{recognition.visual_group_id||'—'}} · Текстовая {{recognition.text_subgroup_id||'—'}}
  </span>
</div>
</template>
