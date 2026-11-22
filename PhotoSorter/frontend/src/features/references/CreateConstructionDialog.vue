<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {regionApi,type Region} from '../../api/regions'
import RegionPicker from '../../components/regions/RegionPicker.vue'
import {referenceApi} from '../../api/references'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import ReferenceDirectoryImporter from './ReferenceDirectoryImporter.vue'
import type {CreatedConstruction} from '../../api/references'

type Mode='standard'|'custom'|'import'
const emit=defineEmits<{
 (e:'dismiss'):void
 (e:'created',sam:string):void
 (e:'noChanges',message:string):void
}>()
const mode=ref<Mode>('standard'),city=ref(''),number=ref(''),address=ref(''),name=ref('')
const regions=ref<Region[]>([])
async function loadRegions(){
 try{
  regions.value=(await regionApi.list()).regions
  if(!city.value)city.value=regions.value[0]?.code||''
 }catch(e){error.value=errorText(e)}
}
onMounted(()=>{void loadRegions()})
const busy=ref(false),importBusy=ref(false),error=ref('')
const title=computed(()=>city.value.trim().toUpperCase()+' '+number.value.trim()+' — '+address.value.trim())
async function save(){
 if(busy.value||importBusy.value)return
 busy.value=true;error.value=''
 try{
  const payload=mode.value==='standard'
    ?{kind:'standard' as const,city_code:city.value.trim().toUpperCase(),number:number.value.trim(),address:address.value.trim()}
    :{kind:'custom' as const,name:name.value.trim()}
  const entry:CreatedConstruction=await referenceApi.createConstruction(payload)
  emit('created',entry.sam)
 }catch(e){error.value=errorText(e)}finally{busy.value=false}
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
      <RegionPicker v-model="city" :regions="regions" label="Регион" @created="loadRegions"/>
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
      <UiButton kind="primary" type="submit" :disabled="mode==='standard'&&!city" :loading="busy">Создать конструкцию</UiButton>
    </div>
   </form>
   <ReferenceDirectoryImporter v-else @no-changes="emit('noChanges',$event)" @checking="importBusy=$event"/>
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
