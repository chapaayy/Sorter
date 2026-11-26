<script setup lang="ts">
import {useSessionStore} from '../../../stores/session'
const session=useSessionStore()
import {onMounted,ref} from 'vue'
import {systemApi} from '../../../api/system'
import {bytes,errorText} from '../../../utils/format'
import {usePolling} from '../../../composables/usePolling'
import type {StorageLimits} from '../../../types/api'
import UiButton from '../../../components/ui/UiButton.vue'
import BudgetSummary from './BudgetSummary.vue'
import {gibValue,parseGib} from './quotaUnits'
const emit=defineEmits<{(e:'refresh'):void}>()
const data=ref<StorageLimits|null>(null),loading=ref(false),saving=ref(false),error=ref(''),message=ref('')
const personal=ref(false),temporary=ref<string|number>(''),reserve=ref<string|number>(''),dirty=ref(false)
function apply(value:StorageLimits){data.value=value;personal.value=value.policy.personal_enabled;temporary.value=gibValue(value.policy.temporary_limit_bytes);reserve.value=gibValue(value.policy.disk_reserve_bytes);dirty.value=false}
async function refresh(){
 if(loading.value||saving.value)return
 loading.value=true
 try{const next=await systemApi.storageLimits();if(dirty.value)data.value=next;else apply(next);error.value=''}
 catch(e){error.value=errorText(e)}finally{loading.value=false}
}
async function save(){
 if(saving.value)return
 saving.value=true;error.value='';message.value=''
 try{
  apply(await systemApi.saveStorageLimits({personal_enabled:personal.value,temporary_limit_bytes:parseGib(temporary.value),disk_reserve_bytes:parseGib(reserve.value)}))
  message.value='Настройки лимитов сохранены';emit('refresh')
 }catch(e){error.value=errorText(e)}finally{saving.value=false}
}
onMounted(()=>void refresh())
usePolling(refresh,15000)
</script>
<template>
<div class="stack">
 <section class="panel stack">
  <div class="row between wrap"><h2>Лимиты хранилища</h2><UiButton :loading="loading" @click="refresh">Обновить</UiButton></div>
  <p v-if="error" role="alert" class="alert error">{{error}}</p>
  <p v-if="message" role="status">{{message}}</p>
  <template v-if="data">
   <p v-if="!data.registry_ready" class="alert warning" role="status">Реестр ещё не готов. Включение новых ограничений доступно после полной фоновой сверки.</p>
   <form class="stack" @submit.prevent="save" @input="dirty=true">
    <label class="row wrap"><input v-model="personal" type="checkbox" aria-label="Включить личные квоты" :disabled="saving||!session.can('storage.configure')"/>Включить личные квоты</label>
    <p class="meta">Индивидуальные значения настраиваются во вкладке «Аккаунты». Без значения аккаунт не ограничен личной квотой. Образцы, постоянные эмбеддинги, модели, ZIP, временные файлы и инфраструктура не относятся к личному объёму.</p>
    <label class="stack meta">Лимит временного пула, ГиБ (пусто — выключено)<input v-model="temporary" aria-label="Лимит временного пула, ГиБ" type="number" min="0" step="any" :disabled="saving||!session.can('storage.configure')"/></label>
    <label class="stack meta">Минимальное свободное место, ГиБ (пусто — штатный резерв)<input v-model="reserve" aria-label="Минимальное свободное место, ГиБ" type="number" min="0" step="any" :disabled="saving||!session.can('storage.configure')"/></label>
    <p class="meta">1 ГиБ = 1024³ байт. Ёмкость диска: {{bytes(data.total_bytes)}}. Штатный минимум: {{bytes(data.disk.baseline_bytes)}}. Для обновлятора дополнительно действует минимум 8 ГиБ. Меньшее значение не ослабляет существующую защиту.</p>
    <p class="meta">Изменение лимита не удаляет данные и не отзывает ранее принятые резервы. Обработка и новые загрузки проверяют доступный бюджет до записи.</p>
    <UiButton v-if="session.can('storage.configure')" kind="primary" type="submit" :loading="saving">Сохранить настройки лимитов</UiButton>
   </form>
  </template>
  <p v-else class="meta">{{loading?'Загружаем лимиты…':'Настройки недоступны.'}}</p>
 </section>
 <template v-if="data">
  <section class="panel stack"><h2>Дисковый резерв</h2><div class="grid2">
   <div><span class="meta">Свободно физически</span><h3>{{bytes(data.disk.free_bytes)}}</h3></div>
   <div><span class="meta">Действующий минимум</span><h3>{{bytes(data.disk.minimum_bytes)}}</h3></div>
   <div><span class="meta">Резервы операций</span><h3>{{bytes(data.disk.reserved_bytes)}}</h3></div>
   <div><span class="meta">Доступно для новых записей</span><h3>{{bytes(data.disk.available_bytes)}}</h3></div>
  </div><p v-if="data.disk.available_bytes===0" class="alert warning" role="status">Достигнут глобальный резерв. Новые записи недоступны.</p></section>
  <section class="panel stack"><BudgetSummary :budget="data.temporary" title="Временный пул"/></section>
 </template>
</div>
</template>
