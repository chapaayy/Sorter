<script setup lang="ts">
import {ref,watch} from 'vue'
import ReferenceDirectoryImporter from './ReferenceDirectoryImporter.vue'
import ReferencePhotoUploader from './ReferencePhotoUploader.vue'

const props=withDefaults(defineProps<{
  selectedSam:string;selectedLabel?:string;initialMode?:'library'|'single'
}>(),{initialMode:'library',selectedLabel:''})
const emit=defineEmits<{
  (e:'finished'):void
  (e:'state',busy:boolean,percent:number,phase:string):void
}>()
const mode=ref<'library'|'single'>(props.initialMode),running=ref(false)
function onState(busy:boolean,percent:number,phase:string){
  running.value=busy
  emit('state',busy,percent,phase)
}
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
       :disabled="running" @click="mode='library'">Библиотека папкой</button>
    <button role="tab" :aria-selected="mode==='single'" :class="{active:mode==='single'}"
       :disabled="running" @click="mode='single'">Фото в конструкцию</button>
  </div>
  <ReferenceDirectoryImporter v-if="mode==='library'" @finished="emit('finished')"
    @state="onState"/>
  <ReferencePhotoUploader v-else :selected-sam="selectedSam"
     :label="selectedLabel||selectedSam" @finished="emit('finished')" @state="onState"/>
</section>
</template>
