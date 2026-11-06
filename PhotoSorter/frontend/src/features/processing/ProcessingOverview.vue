<script setup lang="ts">
import {computed} from 'vue'
import type {ModelInfo,ProcessingSettings,SystemStatus} from '../../types/api'
import {date} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'

const props=defineProps<{
  model:ModelInfo|null
  settings:ProcessingSettings|null
  system:SystemStatus|null
  downloading:boolean
}>()
const emit=defineEmits<{(e:'install'):void}>()
const megaloc=computed(()=>props.model?.models.find(m=>m.id==='megaloc'))
const worker=computed(()=>props.system?.services?.megaloc)
const modelReady=computed(()=>!!megaloc.value?.available)
const workerStatus=computed(()=>!worker.value?'Нет данных':worker.value.alive?'Работает':'Нет сигнала')
</script>
<template>
<section class="panel stack" aria-label="Состояние MegaLoc и настройки">
  <div class="row between wrap">
    <h2 style="margin:0">MegaLoc · CPU</h2>
    <span class="status" :class="modelReady?'ok':''">{{model?modelReady?'Модель установлена':'Модель не установлена':'Проверка модели…'}}</span>
  </div>
  <div class="processing-overview-grid">
    <div class="processing-overview-cell">
      <span class="label">Модель</span>
      <strong>MegaLoc</strong>
      <span class="meta">{{megaloc?.reason||'Единственная доступная для выбора модель'}}</span>
      <UiButton v-if="model&&!modelReady" small :loading="downloading" @click="emit('install')">Установить MegaLoc</UiButton>
    </div>
    <div class="processing-overview-cell">
      <span class="label">MegaLoc Worker</span>
      <strong>{{workerStatus}}</strong>
      <span class="meta">{{worker?.last_seen?'Последний сигнал: '+date(worker.last_seen):'Ожидаем сигнал сервиса'}}</span>
      <span v-if="worker&&!worker.alive" class="meta">При отсутствии сигнала новые задания останутся в очереди.</span>
    </div>
    <div class="processing-overview-cell">
      <span class="label">Настройки новых партий</span>
      <strong>Порог {{settings?.grouping_threshold.toFixed(2)??'—'}}</strong>
      <span class="meta">Автообработка: {{settings?settings.auto_process_new_batches?'Включена':'Выключена':'Загрузка…'}}</span>
      <RouterLink class="meta" to="/settings">Изменить настройки</RouterLink>
    </div>
    <div class="processing-overview-cell">
      <span class="label">Очередь MegaLoc</span>
      <strong>{{system?.worker.queue.queued??'—'}} ожидают</strong>
      <span class="meta">Активных: {{system?(system.worker.queue.running??0)+(system.worker.queue.stopping??0):'—'}}</span>
      <span class="meta">Одновременно выполняется только одно задание</span>
    </div>
  </div>
</section>
