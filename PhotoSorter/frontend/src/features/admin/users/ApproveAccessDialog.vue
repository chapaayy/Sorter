<script setup lang="ts">
import {onMounted,onUnmounted,ref} from 'vue'
import {resultApi,type PublishedResult} from '../../../api/results'
import type { NewUser,AccountOptions } from '../../../api/adminUsers'
import {accountsApi,type Role,type PermissionInfo,type Permissions} from '../../../api/accounts'
import {parseGib} from '../storage/quotaUnits'
import PermissionEditor from './PermissionEditor.vue'
import {date,errorText} from '../../../utils/format'
import UiButton from '../../../components/ui/UiButton.vue'
const props=defineProps<{email?:string;busy:boolean;loadGrants?:()=>Promise<{items:PublishedResult[]}>;creating?:boolean;submitError?:string;configureAccount?:boolean}>()
const emit=defineEmits<{approve:[ids:string[],options?:AccountOptions];create:[payload:NewUser];cancel:[]}>()
const email=ref(''),password=ref(''),confirmation=ref(''),formError=ref('')
const roles=ref<Role[]>([]),catalog=ref<Record<string,PermissionInfo>>({}),roleId=ref('observer'),displayName=ref(''),quota=ref(''),overrides=ref<Permissions>({}),rolesReady=ref(false)
async function loadRoles(){try{const data=await accountsApi.roles();roles.value=data.items.filter(r=>r.id!=='owner');catalog.value=data.catalog;rolesReady.value=true}catch(e){formError.value=errorText(e)}}
const items=ref<PublishedResult[]>([]),chosen=ref<string[]>([]),loading=ref(false),more=ref(false),error=ref('')
const initialized=ref(false),offset=ref(0)
const box=ref<HTMLElement|null>(null)
let previousFocus:HTMLElement|null=null
async function load(){
  if(loading.value)return
  loading.value=true;error.value=''
  try{
    if(!initialized.value&&props.loadGrants){
      const data=await props.loadGrants()
      chosen.value=data.items.map(item=>item.id)
      items.value=data.items
    }
    const data=await resultApi.catalog(30,offset.value)
    offset.value+=data.items.length
    const existing=new Set(items.value.map(item=>item.id))
    items.value.push(...data.items.filter(item=>!existing.has(item.id)));more.value=data.has_more
    initialized.value=true
  }catch(e){error.value=errorText(e)}finally{loading.value=false}
}
function submit(){
  if(props.busy||loading.value||!initialized.value)return
  formError.value=''
  const options:AccountOptions={}
  if(props.creating||props.configureAccount){
    if(!rolesReady.value){formError.value='Сначала загрузите роли';return}
    try{if(roleId.value!=='observer')options.role_id=roleId.value;if(displayName.value.trim())options.display_name=displayName.value.trim();if(quota.value.trim())options.storage_limit_bytes=parseGib(quota.value);if(Object.keys(overrides.value).length)options.overrides=overrides.value}catch(e){formError.value=errorText(e);return}
  }
  if(!props.creating){emit('approve',chosen.value,options);return}
  if(password.value!==confirmation.value){formError.value='Пароли не совпадают.';return}
  emit('create',{email:email.value.trim(),password:password.value,confirmation:confirmation.value,run_ids:chosen.value,...options})
}
function key(event:KeyboardEvent){
  if(event.key==='Escape'&&!props.busy)emit('cancel')
  if(event.key!=='Tab'||!box.value)return
  const focusable=Array.from(box.value.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)'))
  const first=focusable[0],last=focusable[focusable.length-1]
  if(event.shiftKey&&document.activeElement===box.value){event.preventDefault();last?.focus();return}
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
  if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
}
onMounted(()=>{
  previousFocus=document.activeElement instanceof HTMLElement?document.activeElement:null
  box.value?.focus()
  document.addEventListener('keydown',key)
  void load()
  if(props.creating||props.configureAccount)void loadRoles()
})
onUnmounted(()=>{
  document.removeEventListener('keydown',key)
  if(previousFocus?.isConnected)previousFocus.focus()
})
</script>
<template>
  <Teleport to="body"><div class="modal-overlay" @click.self="!busy&&emit('cancel')">
    <form ref="box" tabindex="-1" class="modal stack" role="dialog" aria-modal="true" aria-labelledby="approve-title" @submit.prevent="submit">
      <h2 id="approve-title">{{creating?'Создать пользователя':'Выдать доступ к результатам'}}</h2>
      <div v-if="creating" class="stack-sm">
        <label class="field">Электронная почта или логин<input v-model="email" type="text" autocomplete="off" required maxlength="254" :disabled="busy"/></label>
        <label class="field">Начальный пароль<input v-model="password" type="password" autocomplete="new-password" required minlength="12" maxlength="256" :disabled="busy"/></label>
        <label class="field">Повторите пароль<input v-model="confirmation" type="password" autocomplete="new-password" required minlength="12" maxlength="256" :disabled="busy"/></label>
        <p class="meta">Пароль от 12 символов. Аккаунт будет активен сразу, письмо не отправляется.</p>
      </div>
      <div v-if="(creating||configureAccount)&&rolesReady" class="stack">
        <label class="field">Имя<input v-model="displayName" maxlength="120" :disabled="busy"/></label>
        <label class="field">Роль<select v-model="roleId" :disabled="busy"><option v-for="r in roles" :key="r.id" :value="r.id">{{r.name}}</option></select></label>
        <label class="field">Личная квота, ГиБ (пусто — без ограничения)<input v-model="quota" type="number" min="0" step="any" :disabled="busy"/></label>
        <details><summary>Индивидуальные разрешения</summary><PermissionEditor v-model="overrides" :catalog="catalog" :inherited="roles.find(r=>r.id===roleId)?.permissions||{}" :disabled="busy"/></details>
      </div>
      <button v-else-if="creating||configureAccount" type="button" class="btn small" @click="loadRoles">Загрузить роли</button>
      <p v-if="submitError||formError" class="alert error" role="alert">{{formError||submitError}}</p>
      <p>Выберите, какие отчёты сможет смотреть и скачивать <strong>{{props.email||'пользователь'}}</strong>.</p>
      <p v-if="error" class="alert error" role="alert">{{error}}</p>
      <div class="grant-options">
        <label v-for="item in items" :key="item.id" class="row">
          <input v-model="chosen" type="checkbox" :value="item.id" :disabled="busy||(!chosen.includes(item.id)&&chosen.length>=100)"/>
          <span>{{item.display_name||item.id}} <small class="meta">{{date(item.finished_at)}}</small></span>
        </label>
      </div>
      <p v-if="!loading&&!items.length&&!error" class="meta">Готовых отчётов пока нет. Доступ к ним можно выдать позже.</p>
      <p v-if="initialized&&!chosen.length" class="meta">Выбранные отчёты учитываются только для уровня «Выданные отчёты». Остальные уровни определяются ролью и индивидуальными правами.</p>
      <UiButton v-if="more||loading||error" small :loading="loading" :disabled="busy" @click="load()">{{error?'Повторить':'Показать ещё'}}</UiButton>
      <div class="modal-actions">
        <UiButton :disabled="busy" @click="emit('cancel')">Отмена</UiButton>
        <UiButton kind="primary" :loading="busy" type="submit" :disabled="!initialized||loading||((creating||configureAccount)&&!rolesReady)">{{creating?'Создать':loadGrants?'Сохранить':'Одобрить'}}</UiButton>
      </div>
    </form>
  </div></Teleport>
</template>
<style scoped>
.grant-options{max-height:45vh;overflow:auto;display:grid;gap:8px}
.grant-options label{align-items:flex-start;padding:6px;overflow-wrap:anywhere;cursor:pointer}
</style>
