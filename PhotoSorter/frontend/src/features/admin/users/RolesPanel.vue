<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {accountsApi,type Role,type PermissionInfo,type Permissions} from '../../../api/accounts'
import {errorText} from '../../../utils/format'
import PermissionEditor from './PermissionEditor.vue'
const roles=ref<Role[]>([]),catalog=ref<Record<string,PermissionInfo>>({}),editing=ref(false),id=ref<string|null>(null),name=ref(''),description=ref(''),permissions=ref<Permissions>({}),replacement=ref(''),error=ref(''),busy=ref(false)
async function load(){try{const data=await accountsApi.roles();roles.value=data.items;catalog.value=data.catalog}catch(e){error.value=errorText(e)}}
function open(role?:Role,copy=false){editing.value=true;id.value=role&&!copy?role.id:null;name.value=role?(role.name+(copy?' (копия)':'')):'';description.value=role?.description||'';permissions.value={...role?.permissions};replacement.value='';error.value=''}
async function save(){busy.value=true;error.value='';try{await accountsApi.saveRole(id.value,{name:name.value,description:description.value,permissions:permissions.value});editing.value=false;await load()}catch(e){error.value=errorText(e)}finally{busy.value=false}}
async function remove(){if(!id.value||!window.confirm('Удалить роль? Пользователи получат выбранную замену.'))return;busy.value=true;try{await accountsApi.deleteRole(id.value,replacement.value||null);editing.value=false;await load()}catch(e){error.value=errorText(e)}finally{busy.value=false}}
onMounted(load)
</script>
<template><section class="panel stack"><div class="row between wrap"><h2>Роли</h2><button class="btn primary" @click="open()">Создать роль</button></div><p v-if="error" role="alert" class="alert error">{{error}}</p>
<template v-if="!editing"><div v-for="role in roles" :key="role.id" class="row between wrap"><div><strong>{{role.name}}</strong><p class="meta">{{role.description}} · {{role.users}} аккаунтов</p></div><div class="row wrap" v-if="role.id!=='owner'"><button class="btn small" @click="open(role)">Редактировать</button><button class="btn small" @click="open(role,true)">Копировать</button></div><span v-else class="meta">Защищён</span></div></template>
<form v-else class="stack" @submit.prevent="save"><label class="field">Название<input v-model="name" required maxlength="100"/></label><label class="field">Описание<textarea v-model="description" maxlength="500"/></label><PermissionEditor v-model="permissions" :catalog="catalog" :disabled="busy"/>
<div class="row wrap"><button type="submit" class="btn primary" :disabled="busy">Сохранить роль</button><button type="button" class="btn" @click="editing=false">Отмена</button></div>
<template v-if="id&&!['owner','administrator','employee','observer'].includes(id)"><label class="field">Роль для пользователей при удалении<select v-model="replacement"><option value="">Не выбрана</option><option v-for="r in roles.filter(r=>r.id!==id&&r.id!=='owner')" :key="r.id" :value="r.id">{{r.name}}</option></select></label><button type="button" class="btn danger" :disabled="busy" @click="remove">Удалить роль</button></template></form></section></template>
