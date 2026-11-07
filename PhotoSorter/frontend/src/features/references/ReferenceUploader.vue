<script setup lang="ts">
import {ref,watch} from 'vue'
import ReferenceDirectoryImporter from './ReferenceDirectoryImporter.vue'
import ReferencePhotoUploader from './ReferencePhotoUploader.vue'

const props=withDefaults(defineProps<{
  selectedSam:string;selectedLabel?:string;initialMode?:'library'|'single'
}>(),{initialMode:'library',selectedLabel:''})
const emit=defineEmits<{(e:'finished'):void}>()
const mode=ref<'library'|'single'>(props.initialMode)
watch(()=>props.initialMode,value=>{mode.value=value})
</script>

<template>
<section class="panel stack" aria-label="Загрузка образцов">
  <div class="panel-header">
    <h2>Загрузка образцов</h2>
    <span class="status">Без замены существующих фотографий</span>
  </div>
  <div class="meta" role="status">
    Загрузка доступна во время обработки ФО. Новые образцы попадут в FIFO на подготовку
    и станут доступны только после публикации полной версии.
  </div>
  <div class="segment" role="tablist" aria-label="Способ загрузки образцов">
    <button role="tab" :aria-selected="mode==='library'" :class="{active:mode==='library'}"
      @click="mode='library'">Библиотека папкой</button>
    <button role="tab" :aria-selected="mode==='single'" :class="{active:mode==='single'}"
      @click="mode='single'">Фото в конструкцию</button>
  </div>
  <ReferenceDirectoryImporter v-if="mode==='library'" @finished="emit('finished')"/>
  <ReferencePhotoUploader v-else :selected-sam="selectedSam"
     :label="selectedLabel||selectedSam" @finished="emit('finished')" @state="(busy,percent,phase)=>emit('state',busy,percent,phase)"/>
</section>
</template>
