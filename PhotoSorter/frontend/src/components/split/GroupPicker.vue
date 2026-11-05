<script setup lang="ts">
import {computed,ref} from 'vue'
export interface GroupItem{id:string;label:string;count:number}
const props=defineProps<{items:GroupItem[];modelValue:string;placeholder?:string}>()
const emit=defineEmits<{(e:'update:modelValue',value:string):void}>()
const search=ref('')
const filtered=computed(()=>props.items.filter(i=>i.label.toLowerCase().includes(search.value.toLowerCase())))
</script>
<template>
  <div class="mobile-picker">
    <label class="label" for="mobile-group">Выбрать группу</label>
    <select id="mobile-group" :value="modelValue" @change="emit('update:modelValue',($event.target as HTMLSelectElement).value)">
      <option v-for="item in items" :key="item.id" :value="item.id">{{item.label}} · {{item.count}}</option>
    </select>
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
