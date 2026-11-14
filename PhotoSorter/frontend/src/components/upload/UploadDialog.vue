<script setup lang="ts">
import {onMounted,ref} from 'vue'
defineProps<{title:string;headingId:string}>()
const emit=defineEmits<{(e:'close'):void}>()
const closeButton=ref<HTMLButtonElement|null>(null)
onMounted(()=>closeButton.value?.focus())
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay upload-overlay" @click.self="emit('close')">
      <section class="modal upload-modal" role="dialog" aria-modal="true" :aria-labelledby="headingId">
        <div class="row between upload-modal-header">
          <h2 :id="headingId">{{title}}</h2>
          <button ref="closeButton" type="button" class="btn ghost icon" aria-label="Закрыть окно"
            @click="emit('close')">✕</button>
        </div>
        <slot/>
        <div class="row upload-modal-footer">
          <button type="button" class="btn" @click="emit('close')">Закрыть</button>
        </div>
      </section>
    </div>
  </Teleport>
</template>
