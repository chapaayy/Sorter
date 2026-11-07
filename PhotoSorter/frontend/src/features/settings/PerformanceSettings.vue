<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {runApi} from '../../api/runs'
import type {WorkloadSettings} from '../../types/api'
import {errorText} from '../../utils/format'
import {useNoticeStore} from '../../stores/notice'
import UiButton from '../../components/ui/UiButton.vue'
const data=ref<WorkloadSettings|null>(null),busy=ref(false),error=ref('')
const notice=useNoticeStore()
async function load(){
  try{data.value=await runApi.workloadSettings();error.value=''}
  catch(e){error.value=errorText(e)}
}
onMounted(()=>void load())
async function save(){
  if(!data.value||busy.value)return
  busy.value=true
  try{
    data.value=await runApi.saveWorkloadSettings(
      data.value.mode,data.value.fo_threads,data.value.reference_threads)
    notice.add('Настройки CPU сохранятся для следующих задач','ok');error.value=''
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
<div class="stack gap24">
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <section class="panel stack" v-if="data">
    <div class="row between wrap">
      <div><h2>Вычисления MegaLoc</h2>
        <p class="meta">Изменения применяются к следующей задаче, без прерывания работающей.</p></div>
      <UiButton small :loading="busy" @click="save">Сохранить</UiButton>
    </div>
    <div class="row wrap" style="gap:18px">
      <label class="row" style="gap:7px"><input v-model="data.mode" type="radio" value="auto"/> Автоматически</label>
      <label class="row" style="gap:7px"><input v-model="data.mode" type="radio" value="manual"/> Вручную</label>
    </div>
    <p v-if="data.mode==='auto'" class="meta">Для MegaLoc используется доступный лимит процессора контейнера.</p>
    <template v-else>
      <label class="field">Обработка ФО: {{data.fo_threads}} потоков
        <input v-model.number="data.fo_threads" type="range" min="1" :max="data.max_threads" step="1"/>
      </label>
      <label class="field">Подготовка образцов: {{data.reference_threads}} потоков
        <input v-model.number="data.reference_threads" type="range" min="1" :max="data.max_threads" step="1"/>
      </label>
    </template>
  </section>
  <section class="panel stack">
    <h2>Другие службы</h2>
    <div class="row between wrap">
      <div><strong>Создание миниатюр</strong><p class="meta">Отдельный контейнер, пониженный приоритет</p></div>
      <strong>{{data?.thumbnail_cpu_quota??'—'}} CPU</strong>
    </div>
    <div class="row between wrap">
      <div><strong>Очистка данных</strong><p class="meta">Отдельный фоновый сервис</p></div>
      <strong>{{data?.cleanup_cpu_quota??'—'}} CPU</strong>
    </div>
    <div class="row between wrap">
      <div><strong>ZIP-архив</strong><p class="meta">Без повторного сжатия JPEG, завершающий этап задачи</p></div>
      <span class="meta">Один поток</span>
    </div>
    <p class="meta">Лимиты Docker миниатюр, очистки и общего CPU Worker сейчас задаются в compose.yaml. Интерфейс не меняет их на работающем сервере, чтобы не давать API доступ к Docker.</p>
  </section>
</div>
</template>
