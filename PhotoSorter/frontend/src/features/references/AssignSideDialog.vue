<script setup lang="ts">
import {ref} from 'vue'
import UiButton from '../../components/ui/UiButton.vue'

defineProps<{count:number;busy:boolean}>()
const emit=defineEmits<{
  (event:'assign',side:string):void
  (event:'clear'):void
  (event:'cancel'):void
}>()
const options=['A','A1','A2','A3','B','B1','B2','B3'] as const
const selected=ref<string|null>(null)
</script>
<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="!busy&&emit('cancel')">
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="assign-side-title"
        @keydown.esc.prevent.stop="!busy&&emit('cancel')">
        <h2 id="assign-side-title">Назначить сторону</h2>
        <p class="meta">Выбрано фотографий: {{count}} · Выбери сторону конструкции</p>
        <div class="side-choice-grid" role="group" aria-label="Стороны конструкции">
          <button v-for="option in options" :key="option" type="button"
            class="side-choice" :aria-label="'Сторона '+option"
            :aria-pressed="selected===option" :disabled="busy"
            @click="selected=option">{{option}}</button>
        </div>
        <div class="modal-actions">
          <UiButton :disabled="busy" @click="emit('cancel')">Отмена</UiButton>
          <UiButton :disabled="busy" @click="emit('clear')">Снять сторону</UiButton>
          <UiButton kind="primary" :loading="busy" :disabled="!selected"
            @click="selected&&emit('assign',selected)">Назначить</UiButton>
        </div>
      </section>
    </div>
  </Teleport>
</template>
<style scoped>
.side-choice-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));
  gap:8px;margin:16px 0 20px}
.side-choice{border:1px solid var(--border);border-radius:9px;min-height:44px;
  background:var(--panel-alt);color:var(--text);font-weight:650;cursor:pointer}
.side-choice:hover:not(:disabled){border-color:var(--accent)}
.side-choice[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);
  color:var(--on-accent)}
.side-choice:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
</style>
