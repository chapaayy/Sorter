<script setup lang="ts">
import {computed} from 'vue'
import type {Region} from '../../api/regions'

const props=defineProps<{regions:Region[];modelValue:string[];disabled?:boolean}>()
const emit=defineEmits<{(e:'update:modelValue',codes:string[]):void}>()
const chosen=computed(()=>new Set(props.modelValue))
function toggle(code:string){
  if(props.disabled)return
  const next=chosen.value.has(code)
    ?props.modelValue.filter(x=>x!==code):[...props.modelValue,code]
  emit('update:modelValue',next)
}
function all(){emit('update:modelValue',
  props.modelValue.length===props.regions.length?[]:props.regions.map(r=>r.code))}
</script>
<template>
  <div class="stack-sm">
    <div class="row between wrap">
      <strong>Регионы для обработки</strong>
      <button type="button" class="region-all" :disabled="disabled||!regions.length" @click="all">
        {{modelValue.length===regions.length?'Снять все':'Выбрать все'}}
      </button>
    </div>
    <div class="region-chips" role="group" aria-label="Выбор регионов для обработки">
      <button v-for="region in regions" :key="region.code" type="button"
        :aria-pressed="chosen.has(region.code)" :disabled="disabled"
        @click="toggle(region.code)">{{region.code}}
        <span v-if="chosen.has(region.code)" aria-hidden="true"> ✓</span>
      </button>
    </div>
    <p v-if="!regions.length" class="meta">Пока нет регионов. Сначала добавьте их в «Образцах».</p>
    <p class="meta">Выбрано: {{modelValue.length}} из {{regions.length}}</p>
  </div>
</template>
<style scoped>
.region-chips{display:flex;flex-wrap:wrap;gap:8px}
.region-chips button{min-width:64px;min-height:43px;background:var(--panel-alt);
  border:1px solid var(--border);color:var(--text);border-radius:9px;
  cursor:pointer;font-weight:700;padding:8px 14px}
.region-chips button[aria-pressed=true]{border:2px solid var(--accent);
  background:var(--panel);color:var(--accent)}
.region-chips button:disabled{opacity:.5;cursor:not-allowed}
.region-all{border:0;background:transparent;color:var(--accent);cursor:pointer}
</style>
