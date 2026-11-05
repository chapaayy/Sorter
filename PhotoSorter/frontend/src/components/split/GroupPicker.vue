<script setup lang="ts">
import {computed,ref} from 'vue'
import UiSelect from '../ui/UiSelect.vue'
export interface GroupItem{id:string;label:string;count:number}
const props=defineProps<{items:GroupItem[];modelValue:string;placeholder?:string}>()
const emit=defineEmits<{(e:'update:modelValue',value:string):void}>()
const search=ref('')
const filtered=computed(()=>props.items.filter(i=>i.label.toLowerCase().includes(search.value.toLowerCase())))
</script>
<template>
  <div class="mobile-picker">
    <span class="label">Выбрать группу</span>
    <UiSelect label="Выбрать группу" :model-value="modelValue" :options="items.map(item=>({value:item.id,label:item.label+' · '+item.count}))"
      placeholder="Выберите группу" :disabled="!items.length" @update:model-value="emit('update:modelValue',$event)"/>
  </div>
  <aside class="panel split-aside">
    <input v-model="search" :placeholder="placeholder||'Найти…'" aria-label="Поиск групп" style="margin-bottom:14px"/>
    <nav class="split-list" aria-label="Выбор группы">
      <button v-for="item in filtered" :key="item.id" class="split-item" :class="{active:item.id===modelValue}" :aria-current="item.id===modelValue?'true':undefined" @click="emit('update:modelValue',item.id)">
        <span>{{item.label}}</span><span class="meta">{{item.count}}</span>
      </button>
      <p v-if="!filtered.length" class="meta">Ничего не найдено</p>
    </nav>
  </aside>
</template>
