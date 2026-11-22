<script setup lang="ts">
import {onMounted,ref} from 'vue'
import UiButton from '../../components/ui/UiButton.vue'

defineProps<{count:number;available:string[];busy:boolean}>()
const emit=defineEmits<{
  (event:'assign',side:string):void
  (event:'clear'):void
  (event:'cancel'):void
}>()
const name=ref('')
const field=ref<HTMLInputElement|null>(null)
onMounted(()=>field.value?.focus())
</script>
<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="!busy&&emit('cancel')">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="assign-side-title"
        @keydown.esc.prevent.stop="!busy&&emit('cancel')">
        <h2 id="assign-side-title">Назначить сторону</h2>
        <p class="meta">Выбрано фотографий: {{count}}</p>
        <label class="field">
          <span class="label">Название стороны</span>
          <input ref="field" v-model="name" list="assign-side-existing" maxlength="60"
            placeholder="А, Б, А1…" @keydown.enter.prevent="name.trim()&&!busy&&emit('assign',name)"/>
        </label>
        <datalist id="assign-side-existing">
          <option v-for="side in available" :key="side" :value="side"/>
        </datalist>
        <div class="modal-actions">
          <UiButton :disabled="busy" @click="emit('cancel')">Отмена</UiButton>
          <UiButton :disabled="busy" @click="emit('clear')">Снять сторону</UiButton>
          <UiButton kind="primary" :loading="busy" :disabled="!name.trim()"
            @click="emit('assign',name)">Назначить</UiButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
