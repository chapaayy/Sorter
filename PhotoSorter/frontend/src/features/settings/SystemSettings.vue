<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {systemApi} from '../../api/system'
import {logApi} from '../../api/logs'
import {usePolling} from '../../composables/usePolling'
import {bytes,errorText} from '../../utils/format'
import type {SystemStatus} from '../../types/api'
const system=ref<SystemStatus|null>(null)
const logs=ref<{bytes:number;budget_bytes:number}|null>(null),error=ref('')
async function refresh(){
  try{
    const [s,l]=await Promise.all([systemApi.status(),logApi.usage()])
    system.value=s;logs.value=l;error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>void refresh())
usePolling(refresh,12000)
</script>
<template>
<div class="stack gap24">
  <div v-if="error" class="alert error">{{error}}</div>
  <section class="panel stack">
    <h2>Состояние сервисов</h2>
    <div class="row between"><span class="meta">API / PostgreSQL</span>
      <span class="status" :class="system?'ok':'danger'">{{system?'Доступны':'Нет данных'}}</span></div>
    <div v-for="role in (['megaloc','thumbnail','cleanup'] as const)" :key="role"
      class="row between">
      <span class="meta">{{role==='megaloc'?'MegaLoc Worker':role==='thumbnail'?'Миниатюры':'Очистка'}}</span>
      <span class="status" :class="system?.services?.[role]?.alive?'ok':'danger'">
        {{system?.services?.[role]?.alive?'Работает':'Нет свежего сигнала'}}
      </span>
    </div>
    <div class="row between"><span class="meta">Активных обработок</span>
      <strong>{{system?.worker.queue.running||0}}</strong></div>
    <div class="row between"><span class="meta">Ожидающих ФО</span>
      <strong>{{system?.worker.queue.queued||0}}</strong></div>
    <div class="row between"><span class="meta">Потоков MegaLoc на следующее задание</span>
      <strong>{{system?.worker.expected_threads??'—'}}</strong></div>
    <div class="row between"><span class="meta">API p95</span>
      <strong>{{system?.api.latency.p95_ms??'—'}} мс</strong></div>
  </section>
  <section class="panel stack">
    <h2>Журналы и диагностика</h2>
    <div class="row between"><span class="meta">Использование хранилища журналов</span>
      <strong>{{bytes(logs?.bytes)}} / {{bytes(logs?.budget_bytes)}}</strong></div>
    <RouterLink to="/logs" class="btn" style="align-self:flex-start">Открыть журналы</RouterLink>
  </section>
</div>
</template>
