<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {regionApi,type Region} from '../../api/regions'
import RegionPicker from '../../components/regions/RegionPicker.vue'
import type {SamCount} from '../../types/api'
import {referenceApi,type NewConstruction,type UpdatedConstruction} from '../../api/references'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'

const props=defineProps<{entry:SamCount}>()
const emit=defineEmits<{
  (e:'dismiss'):void
  (e:'saved',entry:UpdatedConstruction):void
}>()
const kind=ref<'standard'|'custom'>(props.entry.kind==='custom'?'custom':'standard')
const city=ref(props.entry.city_code||'')
const regions=ref<Region[]>([])
async function loadRegions(){
 try{regions.value=(await regionApi.list()).regions}
 catch(e){error.value=errorText(e)}
}
onMounted(()=>{void loadRegions()})
const number=ref(props.entry.construction_number||'')
const address=ref(props.entry.address||'')
const name=ref(props.entry.kind==='custom'?props.entry.sam:'')
const busy=ref(false),error=ref('')
const newKey=computed(()=>kind.value==='standard'
  ?city.value.trim().toUpperCase()+' '+number.value.trim()
  :name.value.trim())
const displayName=computed(()=>kind.value==='standard'
  ?newKey.value+' — '+address.value.trim() :newKey.value)
const identityChanged=computed(()=>newKey.value!==props.entry.sam)

async function save(){
  if(busy.value)return
  busy.value=true;error.value=''
  try{
    const data:NewConstruction=kind.value==='standard'
      ?{kind:'standard',city_code:city.value.trim().toUpperCase(),number:number.value.trim(),address:address.value.trim()}
      :{kind:'custom',name:name.value.trim()}
    emit('saved',await referenceApi.updateConstruction(props.entry.sam,data))
  }catch(e){error.value=errorText(e)}
  finally{busy.value=false}
}
</script>
<template>
 <div class="modal-overlay" @click.self="!busy&&emit('dismiss')">
  <form class="modal stack" @submit.prevent="save">
   <h2>Изменить конструкцию</h2>
   <p class="meta">Фотографии останутся в конструкции. Можно изменить номер, город, адрес или тип.</p>
   <div class="segment" role="tablist" aria-label="Тип конструкции">
    <button type="button" role="tab" :aria-selected="kind==='standard'" :disabled="busy"
      @click="kind='standard'">Обычная</button>
    <button type="button" role="tab" :aria-selected="kind==='custom'" :disabled="busy"
      @click="kind='custom'">Индивидуальная</button>
   </div>
   <template v-if="kind==='standard'">
    <div class="grid2">
     <RegionPicker v-model="city" :regions="regions" @created="loadRegions"/>
     <label class="field">Номер конструкции
      <input v-model="number" required maxlength="8" pattern="[0-9]{1,8}"
        placeholder="0004"/></label>
    </div>
    <label class="field">Адрес
     <input v-model="address" required maxlength="120" placeholder="Гагарина 64"/></label>
   </template>
   <label v-else class="field">Индивидуальное название
    <input v-model="name" required minlength="1" maxlength="80"
      placeholder="LED у склада"/></label>
   <div class="construction-dialog-preview">
    <span class="meta">Новое название</span>
    <strong>{{displayName}}</strong>
   </div>
   <p v-if="identityChanged" class="meta">
    При смене номера или названия будет создана новая версия библиотеки. Дождитесь
    завершения очереди перед сохранением. Старые результаты обработки не изменятся.
   </p>
   <div v-if="error" class="alert error" role="alert">{{error}}</div>
   <div class="modal-actions">
    <UiButton :disabled="busy" @click="emit('dismiss')">Отмена</UiButton>
    <UiButton kind="primary" type="submit" :disabled="kind==='standard'&&!city" :loading="busy">Сохранить изменения</UiButton>
   </div>
  </form>
 </div>
</template>
<style scoped>
.construction-dialog-preview{display:grid;gap:6px;padding:14px;background:var(--panel-alt);border:1px solid var(--border-subtle);border-radius:10px;overflow-wrap:anywhere}
.segment{display:flex}
.segment button{flex:1;min-width:0}
input{width:100%;min-width:0}
</style>
