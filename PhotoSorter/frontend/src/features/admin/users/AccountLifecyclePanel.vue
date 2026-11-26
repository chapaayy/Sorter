<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {accountsApi,type Account} from '../../../api/accounts'
import {useSessionStore} from '../../../stores/session'
import {usePolling} from '../../../composables/usePolling'
import {bytes,errorText} from '../../../utils/format'
import UiButton from '../../../components/ui/UiButton.vue'
import ConfirmDialog from '../../../components/ui/ConfirmDialog.vue'
import {ApiError} from '../../../api/client'
const props=defineProps<{account:Account}>()
const emit=defineEmits<{changed:[];deleted:[]}>()
const session=useSessionStore(),data=ref<Awaited<ReturnType<typeof accountsApi.lifecyclePreview>>|null>(null)
const recipient=ref(''),operation=ref('transfer'),options=ref<Account[]>([]),search=ref(''),error=ref(''),busy=ref(false),confirm=ref(false)
const pending=computed(()=>!!data.value?.operation&&data.value.operation.state!=='completed')
let lastState=''

const choices=computed(()=>[...(session.can('accounts.transfer')?[['transfer','Передать личные данные']]:[]),...(session.can('accounts.transfer')&&session.can('accounts.delete')?[['transfer_delete','Передать данные и удалить аккаунт']]:[]),...(session.can('accounts.delete')?[['delete','Удалить аккаунт и личные данные']]:[])])
async function refresh(){try{data.value=await accountsApi.lifecyclePreview(props.account.id);const state=data.value.operation?.state||'';if(state==='completed'&&lastState!=='completed')emit('changed');lastState=state;error.value=''}catch(e){if(e instanceof ApiError&&e.status===404){emit('deleted');return}error.value=errorText(e)}}
async function searchUsers(){try{options.value=(await accountsApi.list(search.value)).items.filter(u=>u.id!==props.account.id&&!u.blocked)}catch(e){error.value=errorText(e)}}
async function execute(){busy.value=true;try{await accountsApi.lifecycle(props.account.id,operation.value,operation.value==='delete'?null:Number(recipient.value),props.account.username);confirm.value=false;await refresh();emit('changed')}catch(e){error.value=errorText(e)}finally{busy.value=false}}
onMounted(()=>{operation.value=choices.value[0]?.[0]||'delete';void refresh();void searchUsers()})
usePolling(refresh,5000)
</script>
<template><section class="stack panel"><h3>Передача и удаление данных</h3><p v-if="error" role="alert" class="alert error">{{error}}</p><template v-if="data"><p>Фотоотчётов: {{data.batches}} · учтено в квоте {{bytes(data.quota.used_bytes)}} · зарезервировано {{bytes(data.quota.reserved_bytes)}}</p><p v-if="data.active_operations" class="meta">Есть активные операции. Для передачи дождитесь их завершения.</p>
<p v-if="pending" role="status">{{data.operation?.state==='retry'?'Ожидает повтора':data.operation?.state==='running'?'Выполняется':'В очереди'}} · {{data.operation?.detail||'Аккаунт заблокирован до завершения операции.'}}</p>
<p v-else-if="data.operation?.state==='completed'" role="status">Передача завершена.</p>
<template v-if="!pending"><label class="field">Действие<select v-model="operation"><option v-for="[key,label] in choices" :key="key" :value="key">{{label}}</option></select></label>
<template v-if="operation!=='delete'"><form class="row wrap" @submit.prevent="searchUsers"><input v-model="search" placeholder="Поиск получателя"/><button class="btn">Найти</button></form><label class="field">Получатель<select v-model="recipient"><option value="">Выберите аккаунт</option><option v-for="u in options" :key="u.id" :value="String(u.id)">{{u.display_name||u.username}}</option></select></label></template>
<p class="meta">Общие образцы и модели не удаляются. Передача требует свободной квоты получателя. При ошибке исходные данные остаются защищены.</p><UiButton kind="danger" :disabled="busy||(operation!=='delete'&&(!recipient||data.active_operations))" @click="confirm=true">Продолжить</UiButton></template></template>
<ConfirmDialog v-if="confirm" title="Подтвердите операцию с аккаунтом" :message="operation==='delete'?'Личные фотоотчёты и результаты будут безвозвратно удалены существующей фоновой службой.':operation==='transfer_delete'?'Личные данные перейдут получателю, исходный аккаунт будет удалён.':'Личные данные перейдут получателю. Исходный аккаунт сохранится.'" :required-text="account.username" danger :busy="busy" confirm-label="Подтвердить" @confirm="execute" @cancel="confirm=false"/></section></template>
