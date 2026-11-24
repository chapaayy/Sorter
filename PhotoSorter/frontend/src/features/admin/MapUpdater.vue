<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref} from 'vue'
import {systemApi} from '../../api/system'
import {bytes,errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import type {MapUpdateStatus} from '../../types/api'

const state=ref<MapUpdateStatus|null>(null),error=ref(''),loading=ref(false)
const phases:Record<string,string>={
  idle:'Готов к проверке',checking:'Проверка GitHub',checked:'Проверка завершена',
  preflight:'Проверка условий',building:'Сборка образа',draining:'Завершение активных операций',
  backup:'Резервная копия',deploying:'Переключение контейнеров',health:'Проверка запуска',
  cleanup:'Очистка сборок',success:'Обновление завершено',failed:'Обновление отменено',
  recovery_required:'Требуется восстановление на сервере'
}
const busy=computed(()=>!!state.value?.busy)
let timer:ReturnType<typeof setInterval>|undefined
let refreshing=false
async function refresh(){
  if(refreshing||loading.value)return
  refreshing=true
  try{const next=await systemApi.updateStatus()
    if(!loading.value){state.value=next;error.value=''}}
  catch(e){error.value=busy.value?'Сайт временно недоступен; состояние обновления проверяется повторно.':errorText(e)}
  finally{refreshing=false}
}
async function run(check:boolean){
  if(!check&&!window.confirm('Обновить MAP из main? Текущие операции завершатся, сайт временно будет недоступен.'))return
  loading.value=true;error.value=''
  try{state.value=await (check?systemApi.checkUpdate():systemApi.startUpdate())}
  catch(e){error.value=errorText(e)}
  finally{loading.value=false}
}
onMounted(()=>{void refresh();timer=setInterval(()=>void refresh(),3000)})
onUnmounted(()=>{if(timer)clearInterval(timer)})
</script>
<template>
  <section class="panel stack" aria-label="Обновление MAP">
    <h2>Обновление MAP</h2>
    <p class="meta">GitHub · main. Служба Ubuntu работает независимо от контейнера сайта.</p>
    <p v-if="error" role="alert" class="meta">{{error}}</p>
    <template v-if="state?.available">
      <div class="row wrap between">
        <span>Установленная версия: <strong>{{state.installed?.slice(0,7)||'не определена'}}</strong></span>
        <span>Новая версия: <strong>{{state.target?.slice(0,7)||'не проверена'}}</strong></span>
      </div>
      <strong role="status">{{phases[state.phase||'idle']||state.phase}}</strong>
      <p v-if="state.detail" class="meta">{{state.detail}}</p>
      <p v-if="state.previous" class="meta">Предыдущая версия сохранена: {{state.previous.slice(0,7)}}.</p>
      <p v-if="state.free_change!=null" class="meta">Изменение свободного места на диске проекта: {{state.free_change>=0?'+':'−'}}{{bytes(Math.abs(state.free_change))}}. Это общий результат, не размер удалённых образов.</p>
      <p v-for="warning in state.warnings||[]" :key="warning" class="meta">{{warning}}</p>
      <p class="meta">Кэш собственной сборки удаляется автоматически. ФО, образцы, результаты, тома PostgreSQL/Caddy и общий старый кэш Docker не очищаются.</p>
      <div class="row wrap">
        <UiButton :disabled="busy||loading||state.phase==='recovery_required'" @click="run(true)">Проверить обновления</UiButton>
        <UiButton :disabled="busy||loading||!state.update_available||state.phase==='recovery_required'" @click="run(false)">Обновить MAP</UiButton>
      </div>
    </template>
    <p v-else class="meta">{{state?.detail||'Проверка службы обновления…'}}</p>
  </section>
</template>
