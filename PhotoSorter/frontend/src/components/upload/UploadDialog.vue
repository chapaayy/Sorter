<script setup lang="ts">
import {nextTick,ref,watch} from 'vue'
const props=defineProps<{
  title:string;visible:boolean;busy:boolean;headingId:string
}>()
const emit=defineEmits<{(e:'close'):void}>()
const closeButton=ref<HTMLButtonElement|null>(null)
watch(()=>props.visible,shown=>{if(shown)void nextTick(()=>closeButton.value?.focus())},{immediate:true})
</script>

<template>
  <Teleport to="body">
    <div v-show="visible" class="modal-overlay upload-overlay" @click.self="emit('close')">
      <section class="modal upload-modal" role="dialog" aria-modal="true" :aria-labelledby="headingId">
        <div class="row between upload-modal-header">
          <h2 :id="headingId">{{title}}</h2>
          <button ref="closeButton" type="button" class="btn ghost icon" aria-label="Свернуть загрузку"
            @click="emit('close')">✕</button>
        </div>
        <slot/>
        <div class="row between upload-modal-footer">
          <span class="meta">{{busy?'Загрузка продолжится после сворачивания':''}}</span>
          <button type="button" class="btn" @click="emit('close')">{{busy?'Свернуть':'Закрыть'}}</button>
        </div>
      </section>
    </div>
  </Teleport>
</template>
