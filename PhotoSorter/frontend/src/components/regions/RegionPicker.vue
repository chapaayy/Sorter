<script setup lang="ts">
import {computed,ref} from 'vue'
import {regionApi,type Region} from '../../api/regions'
import {errorText} from '../../utils/format'
import UiButton from '../ui/UiButton.vue'

const props=withDefaults(defineProps<{
  regions:Region[]
  modelValue:string
  label?:string
  allowAll?:boolean
  allowCustom?:boolean
  disabled?:boolean
}>(),{label:'Регион',allowAll:false,allowCustom:false,disabled:false})
const emit=defineEmits<{
  (e:'update:modelValue',code:string):void
  (e:'created',code:string):void
}>()
const opened=ref(false),query=ref(''),adding=ref(false),code=ref(''),busy=ref(false),error=ref('')
const filtered=computed(()=>props.regions.filter(r=>r.code.includes(query.value.trim().toUpperCase())))
const title=computed(()=>props.modelValue==='*'?'Все регионы':
  props.modelValue==='?'?'Без региона':props.modelValue||'Выбрать регион')
function choose(value:string){emit('update:modelValue',value);opened.value=false;query.value=''}
async function create(){
  if(busy.value)return
  busy.value=true;error.value=''
  try{
    const added=await regionApi.create(code.value.trim().toUpperCase())
    emit('created',added.code)
    choose(added.code);adding.value=false;code.value=''
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
  <div class="region-picker">
    <label class="field-label">{{label}}</label>
    <button type="button" class="region-trigger" :disabled="disabled"
      :aria-expanded="opened" @click="opened=!opened;query='';error=''">
      <strong>{{title}}</strong><span aria-hidden="true">{{opened?'▴':'▾'}}</span>
    </button>
    <div v-if="opened" class="region-popover">
      <input v-model="query" class="region-search" aria-label="Поиск региона"
        placeholder="Поиск кода…"/>
      <div class="region-list" role="listbox" aria-label="Регионы">
        <button v-if="allowAll" type="button" role="option"
          :aria-selected="modelValue==='*'" @click="choose('*')">Все регионы</button>
        <button v-if="allowCustom" type="button" role="option"
          :aria-selected="modelValue==='?'" @click="choose('?')">Без региона</button>
        <button v-for="r in filtered" :key="r.code" type="button" role="option"
          :aria-selected="modelValue===r.code" @click="choose(r.code)">
          <strong>{{r.code}}</strong><span class="meta">{{r.constructions}} констр.</span>
        </button>
        <p v-if="!filtered.length&&!allowAll" class="meta">Ничего не найдено</p>
      </div>
      <div class="region-add">
        <button v-if="!adding" type="button" @click="adding=true">+ Добавить регион</button>
        <div v-else class="region-creation">
          <label class="field">Новый код (2–5 латинских букв)
            <input v-model="code" maxlength="5" minlength="2" pattern="[A-Z]{2,5}"
              @input="code=code.toUpperCase()" placeholder="SZR" required @keydown.enter.prevent="create"/>
          </label>
          <div class="row wrap">
            <UiButton small kind="primary" :loading="busy" @click="create">Добавить</UiButton>
            <UiButton small :disabled="busy" @click="adding=false;error=''">Отмена</UiButton>
          </div>
        </div>
        <div v-if="error" class="alert error" role="alert">{{error}}</div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.region-picker{position:relative;min-width:165px;flex:1;max-width:380px}
.field-label{font-size:12px;color:var(--muted);display:block;margin-bottom:5px}
.region-trigger{display:flex;align-items:center;justify-content:space-between;gap:20px;
  width:100%;padding:11px 13px;border:1px solid var(--border);
  border-radius:10px;background:var(--panel);color:var(--text);cursor:pointer}
.region-popover{position:absolute;top:100%;left:0;width:100%;min-width:230px;z-index:40;
  border:1px solid var(--border);border-radius:10px;background:var(--panel);
  padding:10px;box-shadow:0 10px 28px #0003}
.region-search{width:100%}
.region-list{display:grid;gap:3px;max-height:235px;overflow-y:auto;margin:9px 0}
.region-list button{display:flex;justify-content:space-between;align-items:center;
  padding:9px 10px;text-align:left;border:0;border-radius:7px;cursor:pointer;
  background:transparent;color:var(--text)}
.region-list button:hover,.region-list button[aria-selected=true]{background:var(--panel-alt)}
.region-add{border-top:1px solid var(--border-subtle);padding-top:10px}
.region-add>button{border:0;background:none;color:var(--accent);font-weight:600;cursor:pointer}
.region-creation{display:grid;gap:8px}
.region-add input{max-width:200px}
</style>
