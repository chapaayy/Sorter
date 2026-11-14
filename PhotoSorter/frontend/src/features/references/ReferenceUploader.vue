<script setup lang="ts">
import {ref} from 'vue'
import ReferenceDirectoryImporter from './ReferenceDirectoryImporter.vue'
import ReferencePhotoUploader from './ReferencePhotoUploader.vue'

defineProps<{selectedSam:string;selectedLabel:string}>()
const emit=defineEmits<{
  (e:'noChanges',message:string):void
}>()
const mode=ref<'library'|'single'>('single'),running=ref(false)
</script>

<template>
<section class="panel stack" aria-label="Загрузка образцов">
  <div class="panel-header">
    <h2>Загрузка образцов</h2>
    <span class="status">Без замены существующих фотографий</span>
  </div>
  <div class="meta" role="status">
    Загрузка доступна во время обработки ФО. Новые образцы попадут в общую очередь на подготовку
    и станут доступны только после публикации полной версии.
  </div>
  <div class="segment" role="tablist" aria-label="Способ загрузки образцов">
    <button role="tab" :aria-selected="mode==='library'" :class="{active:mode==='library'}"
       :disabled="running" @click="mode='library'">Библиотека папкой</button>
    <button role="tab" :aria-selected="mode==='single'" :class="{active:mode==='single'}"
       :disabled="running" @click="mode='single'">Фото в конструкцию</button>
  </div>
  <ReferenceDirectoryImporter v-if="mode==='library'" @no-changes="emit('noChanges',$event)" @checking="running=$event"/>
  <ReferencePhotoUploader v-else :selected-sam="selectedSam"
     :label="selectedLabel||selectedSam" @no-changes="emit('noChanges',$event)" @checking="running=$event"/>
</section>
</template>
