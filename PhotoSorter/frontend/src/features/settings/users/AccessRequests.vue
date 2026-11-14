<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {accessRequests,type AccessRequest,type RequestStatus} from '../../../api/accessRequests'
import {date,errorText} from '../../../utils/format'
import UiButton from '../../../components/ui/UiButton.vue'
import ConfirmDialog from '../../../components/ui/ConfirmDialog.vue'
import ApproveAccessDialog from './ApproveAccessDialog.vue'
import {useNoticeStore} from '../../../stores/notice'
const tabs=[{id:'pending',label:'На рассмотрении'},{id:'approved',label:'Одобренные'},{id:'rejected',label:'Отклонённые'}] as const
const tab=ref<RequestStatus>('pending'),items=ref<AccessRequest[]>([]),more=ref(false)
const loading=ref(false),busy=ref(false),error=ref('')
const selected=ref<{item:AccessRequest;approved:boolean;edit?:boolean}|null>(null)
const notice=useNoticeStore()
async function load(append=false){
  if(loading.value)return
  loading.value=true;error.value=''
  if(!append){items.value=[];more.value=false}
  try{
    const data=await accessRequests.list(tab.value,append?items.value.length:0)
    items.value=append?[...items.value,...data.items]:data.items
    more.value=data.has_more
  }catch(e){error.value=errorText(e)}finally{loading.value=false}
}
function selectTab(status:RequestStatus){
  if(loading.value||status===tab.value)return
  tab.value=status
  void load()
}
async function decide(runIds:string[]=[]){
  if(busy.value||!selected.value)return
  busy.value=true;error.value=''
  const {item,approved,edit}=selected.value
  try{
    if(edit)await accessRequests.save(item.id,runIds)
    else await accessRequests.decide(item.id,approved,runIds)
    selected.value=null
    notice.add(edit?'Доступ обновлён':approved?'Заявка одобрена':'Заявка отклонена','ok')
    await load()
  }catch(e){selected.value=null;error.value=errorText(e)}finally{busy.value=false}
}
onMounted(()=>{void load()})
</script>

<template>
  <section class="panel stack">
    <div class="row between wrap">
      <div><h2>Заявки на доступ</h2><p class="meta">Вы выбираете, какие готовые отчёты человек сможет смотреть и скачивать. Почта не подтверждается автоматически.</p></div>
      <UiButton small :disabled="loading||busy" @click="load()">Обновить</UiButton>
    </div>
    <div class="segment row wrap" aria-label="Статус заявок">
      <button v-for="item in tabs" :key="item.id" type="button" :aria-pressed="tab===item.id"
        :disabled="loading||busy" @click="selectTab(item.id)">{{item.label}}</button>
    </div>
    <p v-if="error" class="alert error" role="alert">{{error}}</p>
    <article v-for="item in items" :key="item.id" class="access-request">
      <div class="row between wrap"><strong>{{item.email}}</strong><time class="meta" :datetime="item.created_at">{{date(item.created_at)}}</time></div>
      <p class="access-comment">{{item.comment}}</p>
      <div v-if="item.status==='pending'" class="row wrap">
        <UiButton small kind="primary" @click="selected={item,approved:true}">Одобрить</UiButton>
        <UiButton small @click="selected={item,approved:false}">Отклонить</UiButton>
      </div>
      <UiButton v-else-if="item.status==='approved'" small @click="selected={item,approved:true,edit:true}">Изменить доступ</UiButton>
    </article>
    <p v-if="loading" class="meta" role="status">Загружаем заявки…</p>
    <p v-else-if="!items.length&&!error" class="meta">Заявок пока нет.</p>
    <UiButton v-if="more" small :disabled="loading" @click="load(true)">Показать ещё</UiButton>
  </section>
  <ApproveAccessDialog v-if="selected?.approved" :email="selected.item.email" :busy="busy" :edit-id="selected.edit?selected.item.id:undefined"
    @approve="decide" @cancel="selected=null"/>
  <ConfirmDialog v-else-if="selected" title="Отклонить заявку?"
    :message="selected.item.email+' не получит доступ к MAP.'"
    confirm-label="Отклонить" :busy="busy" danger @confirm="decide()" @cancel="selected=null"/>
</template>

<style scoped>
.access-request{border:1px solid var(--border);border-radius:var(--radius);padding:16px;overflow-wrap:anywhere}
.access-comment{white-space:pre-wrap;margin:12px 0;color:var(--text)}
.segment button[aria-pressed=true]{color:var(--text);background:var(--panel-alt)}
</style>
