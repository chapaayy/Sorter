<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {systemApi} from '../../../api/system'
import {bytes,date,errorText} from '../../../utils/format'
import type {StorageAccountsPage,StorageAccountDetail,StorageCounter} from '../../../types/api'
import UiButton from '../../../components/ui/UiButton.vue'
import LoadingSkeleton from '../../../components/ui/LoadingSkeleton.vue'
import CategoryTable from './CategoryTable.vue'
const page=ref<StorageAccountsPage|null>(null),detail=ref<StorageAccountDetail|null>(null),selected=ref(''),loading=ref(false),error=ref('')
async function load(offset=0){
  if(loading.value)return
  loading.value=true;error.value=''
  try{page.value=await systemApi.storageAccounts(offset)}
  catch(e){error.value=errorText(e)}finally{loading.value=false}
}
async function select(id:string,offset=0){
  if(loading.value)return
  selected.value=id;loading.value=true;error.value='';detail.value=null
  try{detail.value=await systemApi.storageAccount(id,offset)}
  catch(e){error.value=errorText(e)}finally{loading.value=false}
}
const sum=(categories:Record<string,StorageCounter>,key:'allocated_bytes'|'logical_bytes')=>Object.values(categories).reduce((n,r)=>n+r[key],0)
const accountTotal=computed(()=>detail.value?sum(detail.value.categories,'allocated_bytes'):null)
onMounted(()=>void load())
</script>
<template>
<section class="panel stack">
  <div class="row between wrap"><h2>Место по аккаунтам</h2><UiButton :loading="loading" @click="selected?select(selected,detail?.offset??0):load(page?.offset??0)">Обновить</UiButton></div>
  <p class="meta">Личные постоянные данные. Общие образцы и временный пул не относятся к личному объёму. Просмотр чужих результатов не создаёт владение. Лимиты не применяются.</p>
  <p v-if="error" role="alert" class="alert error">{{error}}</p>
  <template v-if="!selected">
    <LoadingSkeleton v-if="loading&&!page" variant="lines" label="Загружаем аккаунты"/>
    <template v-if="page">
      <p class="meta">Снимок: {{date(page.sampled_at)}}{{page.partial?' · неполный':''}}</p>
      <button v-for="user in page.rows" :key="user.id" class="account-row" :disabled="loading" @click="select(user.id)">
        <span><strong>{{user.username}}</strong><small class="meta">{{user.access_role==='owner'?'Владелец':'Пользователь'}}</small></span><span><strong>{{bytes(user.usage?.allocated_bytes)}}</strong><small class="meta">{{bytes(user.usage?.logical_bytes)}} по файлам</small></span>
      </button>
      <p v-if="!page.rows.length" class="meta">Аккаунтов нет.</p>
      <div class="row between wrap"><span class="meta">{{page.total? page.offset+1:0}}–{{page.offset+page.rows.length}} из {{page.total}}</span><div class="row"><UiButton small :disabled="loading||page.offset===0" @click="load(Math.max(0,page.offset-page.limit))">Назад</UiButton><UiButton small :disabled="loading||page.offset+page.rows.length>=page.total" @click="load(page.offset+page.limit)">Дальше</UiButton></div></div>
    </template>
  </template>
  <template v-else>
    <UiButton small :disabled="loading" @click="selected='';detail=null">К аккаунтам</UiButton>
    <LoadingSkeleton v-if="loading" variant="lines" label="Загружаем данные аккаунта"/>
    <template v-if="detail">
      <div class="row between wrap"><h3>{{detail.account.username}}</h3><strong>{{bytes(detail.sampled_at?accountTotal:null)}}</strong></div>
      <p class="meta">Текущие записи реестра; последнее агрегированное измерение: {{date(detail.sampled_at)}}. Hardlink учитывается глобально, поэтому повторная обработка может занимать 0 дополнительных блоков.</p>
      <CategoryTable :categories="detail.categories" :unavailable="!detail.sampled_at"/>
      <h3>Фотоотчёты</h3>
      <p class="meta">Миниатюры могут использоваться несколькими ФО и относятся к аккаунту, а не к отдельной партии.</p>
      <details v-for="batch in detail.batches" :key="batch.batch_id" class="batch-row">
        <summary><strong>{{batch.display_name}}</strong> · {{bytes(detail.sampled_at?sum(batch.categories,'allocated_bytes'):null)}} на диске</summary>
        <p><RouterLink :to="'/fo/'+batch.batch_id">Открыть фотоотчёт</RouterLink></p>
        <CategoryTable :categories="batch.categories" :unavailable="!detail.sampled_at"/>
      </details>
      <p v-if="!detail.batches.length" class="meta">Фотоотчётов нет.</p>
      <div class="row between wrap"><span class="meta">{{detail.total?detail.offset+1:0}}–{{detail.offset+detail.batches.length}} из {{detail.total}}</span><div class="row"><UiButton small :disabled="loading||detail.offset===0" @click="select(selected,Math.max(0,detail.offset-detail.limit))">Назад</UiButton><UiButton small :disabled="loading||detail.offset+detail.batches.length>=detail.total" @click="select(selected,detail.offset+detail.limit)">Дальше</UiButton></div></div>
    </template>
  </template>
</section>
</template>
<style scoped>.account-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(90px,auto);gap:12px;text-align:left;background:var(--panel-alt);color:var(--text);border:1px solid var(--border-subtle);border-radius:9px;padding:12px;cursor:pointer}.account-row span{display:grid;gap:4px;min-width:0;overflow-wrap:anywhere}.account-row span:last-child{text-align:right}.batch-row{padding:12px 0;border-bottom:1px solid var(--border-subtle)}summary{cursor:pointer;overflow-wrap:anywhere}</style>
