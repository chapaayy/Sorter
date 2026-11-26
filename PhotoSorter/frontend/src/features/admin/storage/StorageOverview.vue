<script setup lang="ts">
import {computed} from 'vue'
import {bytes,date} from '../../../utils/format'
import type {StorageUsage,StorageCounter} from '../../../types/api'
import CategoryTable from './CategoryTable.vue'
import {groups} from './labels'
const props=defineProps<{usage:StorageUsage;failed?:boolean}>()
const registry=computed(()=>props.usage.registry)
const host=computed(()=>props.usage.host)
const tree=computed(()=>host.value?.tree_check)
const disk=computed(()=>props.usage.disk_overview??{...props.usage.disk,free_bytes:props.usage.disk.total_bytes-props.usage.disk.used_bytes,map_bytes:null,system_bytes:null,sampled_at:null,system_details:null})
const split=computed(()=>disk.value.map_bytes!==null&&disk.value.system_bytes!==null)
const checking=computed(()=>['queued','running'].includes(props.usage.independent_check?.state||''))
const lastComparable=computed(()=>tree.value?.comparable?tree.value:[...(host.value?.tree_history||[])].reverse().find(r=>r.comparable))
const discrepancy=computed(()=>lastComparable.value?.absolute_discrepancy_bytes)
const realIssue=computed(()=>!!discrepancy.value||!!registry.value?.errors||!!registry.value?.missing_expected||!!registry.value?.cross_owner_inode_conflicts||!!tree.value?.unknown_files||!!host.value?.unknown_sample?.length||Object.values(registry.value?.issues||{}).some(n=>n>0))
const categories=computed(()=>{
  const all:Record<string,StorageCounter>={...registry.value?.categories}
  for(const [key,row] of Object.entries(host.value?.categories||{})){
    const prev=all[key]
    all[key]=prev?{allocated_bytes:prev.allocated_bytes+row.allocated_bytes,logical_bytes:prev.logical_bytes+row.logical_bytes,files:prev.files+row.files,hardlink_paths:prev.hardlink_paths+row.hardlink_paths}:row
  }
  return all
})
const categoryReady=computed(()=>!!registry.value?.sampled_at&&!registry.value.stale&&!!host.value?.at&&!host.value.partial&&!host.value.stale&&Object.keys(registry.value.devices||{}).every(k=>k===String(props.usage.disk.device))&&Object.keys(host.value.devices||{}).every(k=>k===String(props.usage.disk.device)))
const groupTotals=computed(()=>groups.map(g=>({...g,value:g.keys.reduce((n,k)=>n+(categories.value[k]?.allocated_bytes||0),0)})))
const remainder=computed(()=>Object.keys(categories.value).filter(k=>!groups.some(g=>g.keys.includes(k))))
const adjustment=computed(()=>props.usage.disk_overview?.adjustment_bytes)
const directories=computed(()=>props.usage.disk_overview?.directory_bytes)
const pct=(n:number)=>disk.value.total_bytes>0?Math.max(0,Math.min(100,n/disk.value.total_bytes*100)):0
const signed=(n:number)=> (n<0?'−':'+')+bytes(Math.abs(n))
const systemNames:Record<string,string>={docker_engine:'Docker',containerd_default:'containerd',system_logs:'Системные журналы'}
</script>
<template>
  <div class="stack overview">
    <h3>Объём хранилища</h3>
    <div class="metrics">
      <div><span class="meta">Всего</span><strong>{{bytes(disk.total_bytes)}}</strong></div>
      <div><span class="meta">Занято</span><strong>{{bytes(disk.used_bytes)}}</strong></div>
      <div><span class="meta">Свободно</span><strong>{{bytes(disk.free_bytes)}}</strong></div>
    </div>
    <div class="disk-bar" role="img" aria-label="Распределение места на диске">
      <template v-if="split">
        <span class="seg system" :style="{width:pct(disk.system_bytes!)+'%'}"/>
        <span class="seg map" :style="{width:pct(disk.map_bytes!)+'%'}"/>
      </template>
      <span v-else class="seg unknown" :style="{width:pct(disk.used_bytes)+'%'}"/>
      <span class="seg free" :style="{width:pct(disk.free_bytes)+'%'}"/>
    </div>
    <p class="meta">Оперативные показатели: {{date(disk.sampled_at)}}<template v-if="split"> · оценка</template><template v-if="failed||registry?.stale||host?.stale"> · Данные устарели</template><template v-if="!split"> · разбивка пока недоступна</template></p>
    <p class="meta" role="status">Последняя независимая сверка: {{date(tree?.finished_at)}}<template v-if="tree?.comparable&&tree.absolute_discrepancy_bytes!=null"> · расхождение {{bytes(tree.absolute_discrepancy_bytes)}}</template><template v-else-if="tree?.finished_at"> · неполный замер</template><template v-if="checking"> · Проверка учёта…</template></p>
    <p v-if="realIssue" class="alert warning" role="status">{{discrepancy?'Расхождение учёта MAP по последней сопоставимой сверке: '+bytes(discrepancy)+'.':'Обнаружены проблемы учёта MAP. Подробности в диагностике.'}}</p>
    <p v-if="usage.independent_check?.state==='retry'" :class="tree?.errors?'alert warning':'meta'" role="status">{{usage.independent_check.detail||'Проверка будет повторена автоматически.'}}</p>
    <p v-if="usage.disk.warning" class="alert warning" role="status">Мало свободного места на диске.</p>
    <details class="category">
      <summary><span><i class="system"/>Система</span><strong>{{bytes(split?disk.system_bytes:null)}}</strong></summary>
      <template v-if="disk.system_details&&!failed">
        <p class="meta">Отдельный замер корневой ФС: {{date(disk.system_details.sampled_at)}}<template v-if="disk.system_details.system_bytes!==null"> · всего вне MAP {{bytes(disk.system_details.system_bytes)}}</template>.</p>
        <p v-if="disk.system_details.partial" class="meta">Неполный обход: показаны наблюдаемые блоки, остаток не вычислен.</p>
        <div v-for="(amount,key) in disk.system_details.categories" :key="key" class="row between wrap"><span>{{systemNames[key]||key}}</span><strong>{{bytes(amount)}}</strong></div>
        <div v-if="disk.system_details.remaining_bytes!==null" class="row between wrap"><span>Ubuntu и остальные системные данные (остаток)</span><strong>{{bytes(disk.system_details.remaining_bytes)}}</strong></div>
      </template>
      <p v-else class="meta">Подробная разбивка системы пока недоступна; отдельные наблюдения — в диагностике.</p>
    </details>
    <details class="category">
      <summary><span><i class="map"/>MAP</span><strong>{{bytes(split?disk.map_bytes:null)}}</strong></summary>
      <p v-if="!categoryReady||!split" class="meta">Категории предварительные: полный согласованный учёт пока недоступен.</p>
      <p v-else class="meta">Категории реестра и хоста: {{date(registry?.sampled_at)}} / {{date(host?.at)}}.</p>
      <details v-for="g in groupTotals" :key="g.label" class="sub">
        <summary><span>{{g.label}}</span><strong>{{bytes(categoryReady||g.value?g.value:null)}}</strong></summary>
        <CategoryTable :categories="categories" :keys="g.keys" :unavailable="!categoryReady"/>
      </details>
      <details v-if="remainder.length" class="sub"><summary><span>Прочие и неизвестные категории</span><strong>{{bytes(remainder.reduce((n,k)=>n+(categories[k]?.allocated_bytes||0),0))}}</strong></summary><CategoryTable :categories="categories" :keys="remainder"/></details>
      <div class="row between wrap"><span>Блоки каталогов</span><strong>{{bytes(directories)}}</strong></div>
      <p class="meta">Блоки каталогов — последний измеренный объём: {{date(usage.disk_overview?.directory_sampled_at)}}.</p>
      <div v-if="adjustment!=null&&adjustment!==0" class="row between wrap"><span>Поправка по последней независимой сверке</span><strong>{{signed(adjustment)}}</strong></div>
      <p v-if="usage.disk_overview?.preliminary" class="meta">Оперативная оценка может измениться после сверки. Неизмеренные блоки каталогов не подставляются выдуманным значением.</p>
      <p v-if="tree?.absolute_discrepancy_bytes" class="alert warning">Расхождение независимой сверки: {{bytes(tree.absolute_discrepancy_bytes)}}. Не входит в систему.</p>
    </details>
    <details class="category">
      <summary><span><i class="free"/>Свободно</span><strong>{{bytes(disk.free_bytes)}}</strong></summary>
      <p class="meta">Текущие значения для операций MAP:</p>
      <div class="row between wrap"><span>Физически свободно</span><strong>{{bytes(usage.disk.total_bytes-usage.disk.used_bytes)}}</strong></div>
      <div class="row between wrap"><span>Доступно для записи (без резерва ФС)</span><strong>{{bytes(usage.disk.available_bytes)}}</strong></div>
      <div class="row between wrap"><span>Защитный резерв MAP</span><strong>{{bytes(usage.disk.reserved_bytes)}}</strong></div>
      <div class="row between wrap"><span>Резервы активных операций</span><strong>{{bytes(usage.disk.operation_reserved_bytes)}}</strong></div>
      <div class="row between wrap"><span>Доступно для новых операций MAP</span><strong>{{bytes(usage.disk.allocatable_bytes)}}</strong></div>
      <p class="meta">Резервы входят в свободное пространство и не прибавляются к занятому.</p>
    </details>
  </div>
</template>
<style scoped>
.overview{min-width:0}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.metrics>div{display:grid;gap:4px;min-width:0}.metrics strong{font-size:clamp(16px,3vw,23px);overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.disk-bar{height:18px;display:flex;overflow:hidden;border-radius:7px;background:var(--panel-alt);border:1px solid var(--border-subtle)}.seg{height:100%;flex:none}.system{background:#84909f}.map{background:#5679bc}.free{background:#43a18b}.unknown{background:repeating-linear-gradient(135deg,#84909f 0 5px,#aab1ba 5px 10px)}.category,.sub{border-bottom:1px solid var(--border-subtle);padding:8px 0;min-width:0}.category summary,.sub summary{cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:28px;overflow-wrap:anywhere}.category summary::after,.sub summary::after{content:'+';order:3;color:var(--muted)}details[open]>summary::after{content:'−'}.category summary strong,.sub summary strong{margin-left:auto;white-space:nowrap;font-variant-numeric:tabular-nums}.category summary i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:7px}.category[open]>summary,.sub[open]>summary{margin-bottom:8px}.sub{margin-left:12px}.row{gap:6px}
</style>
