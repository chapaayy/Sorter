<script setup lang="ts">
import {useUploadSettingsStore} from '../../stores/uploadSettings'
import UiSelect from '../../components/ui/UiSelect.vue'
const settings=useUploadSettingsStore()
</script>
<template>
<section class="panel stack">
  <h2>Загрузка файлов</h2>
  <p class="meta">Параметры общие для Фотографий и Образцов и применяются при следующем запуске передачи.</p>
  <div class="row between wrap">
    <div><strong>Параллельная загрузка</strong>
      <span class="meta" style="display:block;margin-top:4px">Сколько фотографий передаются одновременно</span>
    </div>
    <div style="width:175px">
      <UiSelect label="Количество параллельных загрузок"
        :model-value="String(settings.parallelUploads)"
        :options="Array.from({length:10},(_,i)=>({value:String(i+1),label:(i+1)+' '+(i+1===1?'поток':i+1<5?'потока':'потоков')}))"
        @update:model-value="settings.parallelUploads=Number($event)"/>
    </div>
  </div>
  <div class="meta">Блоки по 16 МБ. Незавершённые файлы автоматически досылаются после восстановления соединения. После перезагрузки браузера потребуется повторно выбрать исходную папку.</div>
</section>
</template>
