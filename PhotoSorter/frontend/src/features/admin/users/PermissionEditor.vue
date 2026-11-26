<script setup lang="ts">
import {computed,ref} from 'vue'
import {useSessionStore} from '../../../stores/session'
const session=useSessionStore()
import type {PermissionInfo,Permissions,Level} from '../../../api/accounts'
const props=defineProps<{catalog:Record<string,PermissionInfo>;modelValue:Permissions;inherited?:Permissions;disabled?:boolean}>()
const emit=defineEmits<{(e:'update:modelValue',value:Permissions):void}>()
const search=ref('')
const names:Record<Level,string>={none:'Нет',own:'Свои',all:'Все',granted:'Выданные отчёты'}
const groups=computed(()=>Object.entries(props.catalog).filter(([,v])=>v.label.toLowerCase().includes(search.value.toLowerCase())).reduce((a,[k,v])=>{(a[v.group]??=[]).push([k,v]);return a},{} as Record<string,Array<[string,PermissionInfo]>>))
const delegable=(key:string,value:string)=>session.isOwner||value==='none'||((!['accounts.','storage.','system.'].some(prefix=>key.startsWith(prefix))||['system.models','system.processing_view','system.performance_view'].includes(key))&&(session.level(key)==='all'||(session.level(key)===value&&value!=='granted')))
const options=(key:string,info:PermissionInfo)=>(info.scoped?(key.startsWith('results.')?['none','own','all','granted']:['none','own','all']):['none','all']).filter(v=>delegable(key,v)||v===props.modelValue[key])
const label=(key:string,value:Level)=>!props.catalog[key]?.scoped?(value==='none'?'Запретить':'Разрешить'):names[value]
const resolved=(k:string)=>props.modelValue[k]??props.inherited?.[k]??'none'
function change(key:string,value:string){const next={...props.modelValue};if(value==='inherit')delete next[key];else next[key]=value as Level;emit('update:modelValue',next)}
function group(rows:Array<[string,PermissionInfo]>,value:Level|'inherit'){const next={...props.modelValue};for(const [key] of rows){if(value==='inherit')delete next[key];else if(value==='all'){const max=options(key,props.catalog[key]).filter(v=>delegable(key,v));next[key]=(max.includes('all')?'all':max.includes('own')?'own':'none')}else next[key]=value}emit('update:modelValue',next)}
</script>
<template><div class="stack"><input v-model="search" aria-label="Поиск разрешений" placeholder="Поиск разрешений"/>
<details v-for="(rows,name) in groups" :key="name"><summary>{{name}} · {{rows.filter(([k])=>resolved(k)!=='none').length}} / {{rows.length}}</summary>
<div class="row wrap"><button type="button" class="btn small" :disabled="disabled" @click="group(rows,'all')">Разрешить все</button><button type="button" class="btn small" :disabled="disabled" @click="group(rows,'none')">Запретить все</button><button type="button" v-if="inherited" class="btn small" :disabled="disabled" @click="group(rows,'inherit')">По роли</button></div>
<label v-for="[key,info] in rows" :key="key" class="field permission"><span>{{info.label}}</span><select :value="modelValue[key]??(inherited?'inherit':'none')" :disabled="disabled" @change="change(key,($event.target as HTMLSelectElement).value)"><option v-if="inherited" value="inherit">По роли</option><option v-for="value in options(key,info)" :key="value" :value="value">{{label(key,value as Level)}}</option></select><small class="meta">Итог: {{label(key,resolved(key))}}<template v-if="info.requires"> · требуется {{catalog[info.requires]?.label}}</template></small></label></details></div></template>
<style scoped>.permission{padding:10px 0;border-bottom:1px solid var(--border-subtle)}summary{cursor:pointer;margin:8px 0}</style>
