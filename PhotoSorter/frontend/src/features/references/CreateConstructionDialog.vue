<script setup lang="ts">
import {computed,ref} from 'vue'
import {referenceApi} from '../../api/references'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import ReferenceDirectoryImporter from './ReferenceDirectoryImporter.vue'
import type {CreatedConstruction} from '../../api/references'

type Mode='standard'|'custom'|'import'
const emit=defineEmits<{
 (e:'dismiss'):void
 (e:'created',sam:string):void
 (e:'finished',message:string):void
 (e:'state',busy:boolean,percent:number,phase:string):void
}>()
const mode=ref<Mode>('standard'),city=ref('SAM'),number=ref(''),address=ref(''),name=ref('')
const busy=ref(false),importBusy=ref(false),error=ref('')
const title=computed(()=>city.value.trim().toUpperCase()+' '+number.value.trim()+' — '+address.value.trim())
async function save(){
 if(busy.value||importBusy.value)return
 busy.value=true;error.value=''
 emit('state',true,0,'Создаём конструкцию…')
 try{
  const payload=mode.value==='standard'
    ?{kind:'standard' as const,city_code:city.value.trim().toUpperCase(),number:number.value.trim(),address:address.value.trim()}
    :{kind:'custom' as const,name:name.value.trim()}
  const entry:CreatedConstruction=await referenceApi.createConstruction(payload)
  emit('created',entry.sam)
 }catch(e){error.value=errorText(e)}finally{busy.value=false;emit('state',false,0,'')}
}
function importState(running:boolean,percent:number,phase:string){
  importBusy.value=running
  emit('state',running,percent,phase)
}
</script>
<template>
  <div class="construction-dialog">
   <div class="segment construction-dialog-tabs" role="tablist" aria-label="Способ создания">
    <button type="button" role="tab" :aria-selected="mode==='standard'" :disabled="busy||importBusy" @click="mode='standard'">Обычная</button>
    <button type="button" role="tab" :aria-selected="mode==='custom'" :disabled="busy||importBusy" @click="mode='custom'">Индивидуальная</button>
    <button type="button" role="tab" :aria-selected="mode==='import'" :disabled="busy||importBusy" @click="mode='import'">Импорт папки</button>
   </div>
   <form v-if="mode!=='import'" class="stack" @submit.prevent="save">
    <template v-if="mode==='standard'">
     <div class="grid2">
      <label class="field">Код города
       <input v-model.trim="city" @input="city=city.toUpperCase()" required
         minlength="2" maxlength="5" pattern="[A-Z]{2,5}"
         autocapitalize="characters" autocomplete="off" :spellcheck="false"
         placeholder="SAM, MSK, KZN"/>
       <span class="meta">Любой код из 2–5 латинских букв</span>
      </label>
      <label class="field">Номер конструкции
       <input v-model="number" required maxlength="8" pattern="[0-9]{1,8}" placeholder="0004"/></label>
     </div>
     <label class="field">Адрес конструкции
      <input v-model="address" required maxlength="120" placeholder="Гагарина 64"/></label>
     <div class="construction-dialog-preview"><span class="meta">Итоговое название</span>
      <strong>{{title}}</strong></div>
    </template>
    <template v-else>
     <label class="field">Индивидуальное название
      <input v-model="name" required minlength="1" maxlength="80" placeholder="Самореклама офис"/></label>
     <p class="meta">Свободное название без номера и адреса. После создания можно добавить фотографии — они пройдут обычную подготовку MegaLoc.</p>
    </template>
    <div v-if="error" class="alert error" role="alert">{{error}}</div>
    <div class="modal-actions"><UiButton :disabled="busy" @click="emit('dismiss')">Отмена</UiButton>
      <UiButton kind="primary" type="submit" :loading="busy">Создать конструкцию</UiButton>
    </div>
   </form>
   <ReferenceDirectoryImporter v-else @finished="emit('finished',$event)" @state="importState"/>
  </div>
</template>
<style scoped>
.construction-dialog{display:grid;gap:20px}
.construction-dialog-tabs{display:flex;width:100%}
.construction-dialog-tabs button{flex:1;min-width:0;padding:10px 7px;font-size:12px}
.construction-dialog-preview{display:grid;gap:6px;padding:14px;background:var(--panel-alt);border:1px solid var(--border-subtle);border-radius:10px;overflow-wrap:anywhere}
.construction-dialog input,.construction-dialog select{width:100%;min-width:0}
@media(max-width:520px){.construction-dialog-tabs{flex-wrap:wrap}.construction-dialog-tabs button{flex:1 1 40%}}
</style>
