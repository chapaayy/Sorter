<script setup lang="ts">
import {ref} from 'vue'
import ReferenceDirectoryImporter from './ReferenceDirectoryImporter.vue'
import ReferencePhotoUploader from './ReferencePhotoUploader.vue'

const props=defineProps<{selectedSam:string;selectedLabel:string;initialMode:'library'|'single'}>()
const emit=defineEmits<{
  (e:'finished',message:string):void
  (e:'state',busy:boolean,percent:number,phase:string):void
}>()
const mode=ref(props.initialMode),running=ref(false)
function onState(busy:boolean,percent:number,phase:string){
  running.value=busy
  emit('state',busy,percent,phase)
}
</script>

<template>
<section class="panel stack" aria-label="Загрузка образцов">
  <div class="meta" role="status">
    Загрузка доступна во время обработки ФО. Новые образцы попадут в общую очередь на подготовку
    и станут доступны только после публикации полной версии.
  </div>
  <div v-if="selectedSam" class="segment" role="tablist" aria-label="Способ загрузки образцов">
    <button role="tab" :aria-selected="mode==='library'" :class="{active:mode==='library'}"
       :disabled="running" @click="mode='library'">Библиотека папкой</button>
    <button role="tab" :aria-selected="mode==='single'" :class="{active:mode==='single'}"
       :disabled="running" @click="mode='single'">Фото в конструкцию</button>
  </div>
  <ReferenceDirectoryImporter v-if="mode==='library'" @finished="emit('finished',$event)" @state="onState"/>
  <ReferencePhotoUploader v-else :selected-sam="selectedSam"
     :label="selectedLabel||selectedSam" @finished="emit('finished',$event)" @state="onState"/>
</section>
</template>
