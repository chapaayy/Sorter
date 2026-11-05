<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {batchApi} from '../../api/batches'
import {systemApi} from '../../api/system'
import {logApi} from '../../api/logs'
import {runApi} from '../../api/runs'
import {useThemeStore} from '../../stores/theme'
import {useNoticeStore} from '../../stores/notice'
import {usePolling} from '../../composables/usePolling'
import type {Batch,StorageUsage,SystemStatus,ModelInfo,ThemeChoice} from '../../types/api'
import {bytes,date,errorText} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import UiButton from '../../components/ui/UiButton.vue'
import ConfirmDialog from '../../components/ui/ConfirmDialog.vue'
const theme=useThemeStore(),notice=useNoticeStore()
const usage=ref<StorageUsage|null>(null),system=ref<SystemStatus|null>(null),logs=ref<{bytes:number;budget_bytes:number}|null>(null),
 model=ref<ModelInfo|null>(null),batches=ref<Batch[]>([]),error=ref(''),busy=ref(false),cleanConfirm=ref(false)
const due=computed(()=>batches.value.filter(b=>b.delete_state==='active'&&b.delete_after_at).sort((a,b)=>(a.delete_after_at||'').localeCompare(b.delete_after_at||'')))
const categoryNames:Record<string,string>={photos:'Оригиналы ФО',results:'Готовые результаты',references:'Образцы',thumbnails:'Миниатюры',reference_cache:'Кэш MegaLoc',models:'Модели',logs:'Журналы',runs:'Состояния запусков',incoming:'Временные загрузки',other:'Прочее'}
async function refresh(){
  try{
    const [u,s,l,m,b]=await Promise.all([systemApi.usage(),systemApi.status(),logApi.usage(),runApi.models(),batchApi.list(200)])
    usage.value=u;system.value=s;logs.value=l;model.value=m;batches.value=b.batches;error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>{void refresh()})
usePolling(refresh,15000)
async function extend(batchId:string){
  busy.value=true
  try{await batchApi.extend(batchId);notice.add('Хранение продлено ещё на 2 месяца','ok');await refresh()}
  catch(e){error.value=errorText(e)}finally{busy.value=false}
}
async function cleanup(){
  busy.value=true
  try{
    const result=await systemApi.cleanup()
    cleanConfirm.value=false;notice.add('Удалено неиспользуемых превью: '+result.removed,'ok')
    await refresh()
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<PageHeader eyebrow="ПАРАМЕТРЫ И СОСТОЯНИЕ" title="Настройки" subtitle="Только необходимые параметры, состояние сервера и сроки хранения."/>
<div v-if="error" class="alert error" role="alert" style="margin-bottom:18px">{{error}}</div>
<div class="stack gap24">
  <section class="panel stack">
    <h2>Оформление</h2><p class="meta">Тема применяется ко всем страницам, диалогам и просмотрщику.</p>
    <div class="segment" role="radiogroup" aria-label="Тема сайта">
      <button v-for="value in (['system','dark','light'] as ThemeChoice[])" :key="value" role="radio" :aria-checked="theme.choice===value" :class="{active:theme.choice===value}" @click="theme.choice=value">{{value==='system'?'Системная':value==='dark'?'Тёмная':'Светлая'}}</button>
    </div>
  </section>
  <section class="panel stack">
    <div class="panel-header"><h2>Хранилище</h2><span v-if="usage?.disk.warning" class="status" :class="usage.disk.warning==='critical'?'danger':''">{{usage.disk.warning==='critical'?'Критично: ≥90%':'Предупреждение: ≥80%'}}</span></div>
    <template v-if="usage">
      <div class="row between wrap"><strong style="font-size:22px">{{bytes(usage.disk.used_bytes)}} / {{bytes(usage.disk.total_bytes)}}</strong><span class="meta">Свободно: {{bytes(usage.disk.available_bytes)}}</span></div>
      <div class="progress-track" role="progressbar" :aria-valuenow="Math.round(usage.disk.used_fraction*100)" aria-valuemin="0" aria-valuemax="100"><span class="progress-fill" :style="{width:Math.min(100,usage.disk.used_fraction*100)+'%'}"/></div>
      <div class="meta">Системный резерв: {{bytes(usage.disk.reserved_bytes)}} · расчёт на основе реального mount.</div>
      <div class="grid3">
        <div v-for="(value,key) in usage.categories_bytes" :key="key" class="row between" style="padding:9px 0;border-bottom:1px solid var(--border-subtle)"><span class="meta">{{categoryNames[key]||key}}</span><strong>{{bytes(value)}}</strong></div>
        <div class="row between" style="padding:9px 0;border-bottom:1px solid var(--border-subtle)"><span class="meta">PostgreSQL (оценка)</span><strong>{{bytes(usage.database_estimated_bytes)}}</strong></div>
      </div>
      <div class="meta">Двойной учёт Hard Links исключён по inode. WAL, Docker и Caddy на отдельных томах не оцениваются как будто это те же данные.</div>
    </template>
    <p v-else class="meta">Загружаем реальную статистику…</p>
  </section>
  <section class="panel stack">
    <div class="panel-header"><h2>Автоматическая очистка</h2><span class="status">2 месяца · предупреждение за 7 дней</span></div>
    <p class="meta">Срок отсчитывается только после отдельного подтверждения сохранённого полного ZIP. Неподтверждённые партии не удаляются по этому таймеру.</p>
    <div v-for="batch in due" :key="batch.batch_id" class="row between wrap" style="border-bottom:1px solid var(--border-subtle);padding:10px 0">
      <div><RouterLink :to="'/fo/'+batch.batch_id"><strong>{{batch.display_name}}</strong></RouterLink><div class="meta">Удаление: {{date(batch.delete_after_at)}}</div></div>
      <UiButton small :loading="busy" @click="extend(batch.batch_id)">+ 2 месяца</UiButton>
    </div>
    <div v-if="!due.length" class="meta">Нет партий с подтверждённым ZIP и назначенным удалением.</div>
    <div class="row between wrap"><p class="meta" style="margin:0">Ручная очистка удаляет только кэш миниатюр без владельцев и старые временные WebP. Образцы, оригиналы и результаты не затрагиваются.</p><UiButton @click="cleanConfirm=true">Очистить неиспользуемое</UiButton></div>
  </section>
  <div class="grid2">
    <section class="panel stack">
      <h2>Состояние системы</h2>
      <div class="row between"><span class="meta">API</span><span class="status" :class="system?'ok':''">{{system?'Отвечает':'Нет данных'}}</span></div>
      <div class="row between"><span class="meta">PostgreSQL</span><span class="status" :class="system?'ok':''">{{system?'Доступен':'Нет данных'}}</span></div>
      <div class="row between"><span class="meta">Задачи MegaLoc</span><strong>{{system?.worker.queue.running||0}} выполняется · {{system?.worker.queue.queued||0}} ожидает</strong></div>
      <div class="row between"><span class="meta">Миниатюры</span><strong>{{system?.thumbnails.queued||0}} в очереди</strong></div>
      <div class="row between"><span class="meta">API p95 (последние запросы)</span><strong>{{system?.api.latency.p95_ms??'—'}} мс</strong></div>
      <div class="meta">Независимый heartbeat Worker пока не предоставляется API. Пустая очередь не доказывает, что процесс работает.</div>
    </section>
    <section class="panel stack">
      <h2>MegaLoc и журналы</h2>
      <div class="row between"><span class="meta">Модель</span><strong>{{model?.models[0]?.title||'—'}}</strong></div>
      <div class="row between"><span class="meta">Файлы весов</span><span class="status" :class="model?.models[0]?.available?'ok':'danger'">{{model?.models[0]?.available?'Обнаружены':'Не найдены'}}</span></div>
      <div class="row between"><span class="meta">Устройство</span><strong>{{model?.device||'—'}}</strong></div>
      <div class="row between"><span class="meta">Журналы</span><strong>{{bytes(logs?.bytes)}} / {{bytes(logs?.budget_bytes)}}</strong></div>
      <div class="meta">Подпись текущих весов, если не возвращается API, не отображается как проверенная.</div>
      <RouterLink to="/logs" class="btn">Открыть логи →</RouterLink>
    </section>
  </div>
  <section class="panel stack">
    <h2>Резервные копии</h2>
    <div class="alert warning">Автоматическое внешнее резервное копирование не подтверждено доступным API. Последнюю успешную offsite-копию невозможно проверить из этой панели.</div>
    <p class="meta">Перед обновлением или переносом VPS требуется согласованный backup PostgreSQL, PhotoSorter/data и Models, а также тест восстановления. Не используйте «down -v».</p>
    <a class="btn" href="https://github.com/chapaayy/Sorter/blob/stage3/vue-frontend/docs/BACKUP_RESTORE.md" target="_blank" rel="noopener noreferrer" style="align-self:start">Инструкция по бэкапам ↗</a>
  </section>
</div>
<ConfirmDialog v-if="cleanConfirm" title="Очистить только неиспользуемый кэш?" message="Будут удалены только не принадлежащие ни одному фото миниатюры и устаревшие временные WebP. Оригиналы ФО и Образцы не затрагиваются." confirm-label="Очистить кэш" :busy="busy" @cancel="cleanConfirm=false" @confirm="cleanup"/>
</template>
