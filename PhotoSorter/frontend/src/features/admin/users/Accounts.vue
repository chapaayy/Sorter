<script setup lang="ts">
import {onMounted,ref,watch} from 'vue'
import {adminUsers,type ManagedUser,type NewUser} from '../../../api/adminUsers'
import {date,errorText} from '../../../utils/format'
import UiButton from '../../../components/ui/UiButton.vue'
import LoadingSkeleton from '../../../components/ui/LoadingSkeleton.vue'
import {useNoticeStore} from '../../../stores/notice'
import ApproveAccessDialog from './ApproveAccessDialog.vue'

const props=defineProps<{refreshKey:number}>()
const emit=defineEmits<{created:[]}>()
const notice=useNoticeStore()
const accounts=ref<ManagedUser[]>([]),more=ref(false),loading=ref(false),error=ref('')
const creating=ref(false),editing=ref<ManagedUser|null>(null),busy=ref(false),submitError=ref('')
let refreshPending=false
async function load(append=false){
  if(loading.value){if(!append)refreshPending=true;return}
  loading.value=true;error.value=''
  try{
    const data=await adminUsers.list(append?accounts.value.length:0)
    accounts.value=append?[...accounts.value,...data.items]:data.items
    more.value=data.has_more
  }catch(e){error.value=errorText(e)}
  finally{
    loading.value=false
    if(refreshPending){refreshPending=false;void load()}
  }
}
function close(){creating.value=false;editing.value=null;submitError.value=''}
async function create(payload:NewUser){
  if(busy.value)return
  busy.value=true;submitError.value=''
  try{
    const user=await adminUsers.create(payload)
    close();emit('created')
    notice.add('Аккаунт '+user.email+' создан','ok')
    await load()
  }catch(e){submitError.value=errorText(e)}finally{busy.value=false}
}
async function save(ids:string[]){
  if(!editing.value||busy.value)return
  busy.value=true;submitError.value=''
  try{
    await adminUsers.save(editing.value.id,ids)
    close();notice.add('Доступ обновлён','ok')
  }catch(e){submitError.value=errorText(e)}finally{busy.value=false}
}
onMounted(()=>void load())
watch(()=>props.refreshKey,()=>void load())
</script>

<template>
  <section class="panel stack" aria-label="Аккаунты">
    <div class="row between wrap">
      <div><h2>Аккаунты</h2><p class="meta">Создавайте аккаунты без заявки и меняйте доступ к готовым отчётам.</p></div>
      <UiButton kind="primary" @click="creating=true">Создать пользователя</UiButton>
    </div>
    <p v-if="error" class="alert error" role="alert">{{error}} <UiButton small @click="load()">Повторить</UiButton></p>
    <article v-for="user in accounts" :key="user.id" class="row between wrap account-row">
      <div><strong>{{user.email}}</strong> <time class="meta" :datetime="user.created_at">{{date(user.created_at)}}</time></div>
      <UiButton small @click="editing=user">Изменить доступ</UiButton>
    </article>
    <LoadingSkeleton v-if="loading&&!accounts.length" variant="lines" :count="2" label="Загружаем аккаунты"/>
    <p v-else-if="!accounts.length&&!error" class="meta">Аккаунтов пока нет.</p>
    <UiButton v-if="more" small :disabled="loading" @click="load(true)">Показать ещё</UiButton>
  </section>
  <ApproveAccessDialog v-if="creating" creating :busy="busy" :submit-error="submitError" @create="create" @cancel="close"/>
  <ApproveAccessDialog v-else-if="editing" :email="editing.email" :busy="busy" :submit-error="submitError"
    :load-grants="()=>adminUsers.grants(editing!.id)" @approve="save" @cancel="close"/>
</template>

<style scoped>
.account-row{padding:12px 0;border-top:1px solid var(--border);overflow-wrap:anywhere}
.account-row time{margin-inline-start:8px}
</style>
