<script setup lang="ts">
import {computed} from 'vue'
import {bytes} from '../../../utils/format'
import type {StorageBudget} from '../../../types/api'
const props=defineProps<{budget:StorageBudget;title:string}>()
const labels={unlimited:'Без ограничения',ok:'В пределах лимита',warning:'Приближение к лимиту',full:'Лимит достигнут',exceeded:'Лимит превышен'}
const ratio=(n:number)=>props.budget.limit_bytes?Math.max(0,Math.min(100,n/props.budget.limit_bytes*100)):0
const used=computed(()=>ratio(props.budget.used_bytes))
const reserved=computed(()=>Math.min(100-used.value,ratio(props.budget.reserved_bytes)))
</script>
<template>
<div class="quota-summary stack">
  <div class="row between wrap"><strong>{{title}}</strong><span :class="['status',budget.state==='ok'?'ok':'']">{{labels[budget.state]}}</span></div>
  <div v-if="budget.enabled" class="quota-bar" role="img" :aria-label="'Занято '+bytes(budget.used_bytes)+', зарезервировано '+bytes(budget.reserved_bytes)+' из '+bytes(budget.limit_bytes)"><span class="used" :style="{width:used+'%'}"/><span class="reserved" :style="{width:reserved+'%'}"/></div>
  <div class="quota-metrics">
    <div><span class="meta">Занято</span><strong>{{bytes(budget.used_bytes)}}</strong></div>
    <div><span class="meta">Зарезервировано</span><strong>{{bytes(budget.reserved_bytes)}}</strong></div>
    <div><span class="meta">Лимит</span><strong>{{budget.limit_bytes==null?'Нет':bytes(budget.limit_bytes)}}</strong></div>
    <div><span class="meta">Доступно</span><strong>{{budget.enabled?bytes(budget.available_bytes):'Без лимита'}}</strong></div>
  </div>
  <p v-if="budget.state==='warning'||budget.state==='full'||budget.state==='exceeded'" class="alert warning" role="status">Новые операции могут быть отклонены из-за ограничения. Уже принятые резервы сохраняются; данные не удаляются.</p>
  <p v-if="!budget.enabled&&budget.limit_bytes!=null" class="meta">Лимит сохранён, но не применяется.</p>
</div>
</template>
<style scoped>
.quota-summary{padding:12px;border:1px solid var(--border-subtle);border-radius:9px}.quota-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:10px}.quota-metrics>div{display:grid;gap:4px;min-width:0}.quota-metrics strong{overflow-wrap:anywhere}.quota-bar{height:12px;border-radius:5px;background:var(--panel-alt);display:flex;overflow:hidden}.quota-bar span{flex:none}.used{background:#5679bc}.reserved{background:#d59749}
</style>
