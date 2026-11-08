<script setup lang="ts">
import type {ResultView} from '../../types/resultViews'
const props=defineProps<{modelValue:ResultView;adEnabled:boolean}>()
const emit=defineEmits<{(e:'update:modelValue',value:ResultView):void}>()
const sorting: {id:ResultView;label:string}[]=[
  {id:'sam',label:'По конструкциям'}, {id:'group',label:'По группам ФО'}
]
const advertising: {id:ResultView;label:string}[]=[
  {id:'screens',label:'По экранам'},
  {id:'visual-groups',label:'По рекламе (группы)'},
  {id:'ads',label:'По рекламе'},
  {id:'ocr',label:'По рекламе (Текст)'},
  {id:'comparisons',label:'Сравнения'}
]
</script>
<template>
<nav class="panel result-views-nav" aria-label="Режимы просмотра результатов">
  <div class="result-views-row">
    <span class="eyebrow">Основная сортировка</span>
    <div class="segment result-views-tabs" role="tablist" aria-label="Основная сортировка">
      <button v-for="item in sorting" :key="item.id" type="button" role="tab"
        :aria-selected="props.modelValue===item.id"
        @click="emit('update:modelValue',item.id)">{{item.label}}</button>
    </div>
  </div>
  <div class="result-views-row">
    <span class="eyebrow">Распознавание рекламы <span v-if="!adEnabled" class="meta">· не включено для этого запуска</span></span>
    <div class="segment result-views-tabs" role="tablist" aria-label="Распознавание рекламы">
      <button v-for="item in advertising" :key="item.id" type="button" role="tab"
        :aria-selected="props.modelValue===item.id"
        @click="emit('update:modelValue',item.id)">{{item.label}}</button>
    </div>
  </div>
</nav>
</template>
