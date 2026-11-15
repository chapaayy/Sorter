<script setup lang="ts">
import {onMounted,onUnmounted,ref} from 'vue'
import {resultApi,type PublishedResult} from '../../../api/results'
import {accessRequests} from '../../../api/accessRequests'
import {date,errorText} from '../../../utils/format'
import UiButton from '../../../components/ui/UiButton.vue'
const props=defineProps<{email:string;busy:boolean;editId?:string}>()
const emit=defineEmits<{approve:[ids:string[]];cancel:[]}>()
const items=ref<PublishedResult[]>([]),chosen=ref<string[]>([]),loading=ref(false),more=ref(false),error=ref('')
const initialized=ref(false),offset=ref(0)
const box=ref<HTMLElement|null>(null)
let previousFocus:HTMLElement|null=null
async function load(){
  if(loading.value)return
  loading.value=true;error.value=''
  try{
    if(!initialized.value&&props.editId){
      const data=await accessRequests.grants(props.editId)
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
function key(event:KeyboardEvent){
  if(event.key==='Escape'&&!props.busy)emit('cancel')
  if(event.key!=='Tab'||!box.value)return
  const focusable=Array.from(box.value.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled)'))
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
})
onUnmounted(()=>{
  document.removeEventListener('keydown',key)
  if(previousFocus?.isConnected)previousFocus.focus()
})
</script>
<template>
  <Teleport to="body"><div class="modal-overlay" @click.self="!busy&&emit('cancel')">
    <section ref="box" tabindex="-1" class="modal stack" role="dialog" aria-modal="true" aria-labelledby="approve-title">
      <h2 id="approve-title">Выдать доступ к результатам</h2>
      <p>Выберите, какие отчёты сможет смотреть и скачивать <strong>{{email}}</strong>.</p>
      <p v-if="error" class="alert error" role="alert">{{error}}</p>
      <div class="grant-options">
        <label v-for="item in items" :key="item.id" class="row">
          <input v-model="chosen" type="checkbox" :value="item.id" :disabled="busy||(!chosen.includes(item.id)&&chosen.length>=100)"/>
          <span>{{item.display_name||item.id}} <small class="meta">{{date(item.finished_at)}}</small></span>
        </label>
      </div>
      <p v-if="!loading&&!items.length&&!error" class="meta">Готовых отчётов пока нет. Доступ к ним можно выдать позже.</p>
      <p v-if="initialized&&!chosen.length" class="meta">Без выбранных отчётов пользователь сможет войти, но ничего не увидит.</p>
      <UiButton v-if="more||loading||error" small :loading="loading" :disabled="busy" @click="load()">{{error?'Повторить':'Показать ещё'}}</UiButton>
      <div class="modal-actions">
        <UiButton :disabled="busy" @click="emit('cancel')">Отмена</UiButton>
        <UiButton kind="primary" :loading="busy" :disabled="!initialized||loading" @click="emit('approve',chosen)">{{editId?'Сохранить':'Одобрить'}}</UiButton>
      </div>
    </section>
  </div></Teleport>
</template>
<style scoped>
.grant-options{max-height:45vh;overflow:auto;display:grid;gap:8px}
.grant-options label{align-items:flex-start;padding:6px;overflow-wrap:anywhere;cursor:pointer}
</style>
