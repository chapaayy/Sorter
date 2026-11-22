<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {regionApi,type Region} from '../../api/regions'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
import RegionChips from '../../components/regions/RegionChips.vue'

defineProps<{busy:boolean}>()
const emit=defineEmits<{(event:'confirm',codes:string[]):void;(event:'cancel'):void}>()
const regions=ref<Region[]>([]),selected=ref<string[]>([]),error=ref(''),loading=ref(true)
onMounted(async()=>{
  try{regions.value=(await regionApi.list()).regions}
  catch(e){error.value=errorText(e)}
  finally{loading.value=false}
})
</script>
<template>
  <div class="modal-overlay" @click.self="!busy&&emit('cancel')">
    <section class="modal stack" role="dialog" aria-modal="true" aria-label="Выбор регионов для обработки"
      @keydown.esc.stop.prevent="!busy&&emit('cancel')">
      <h2>Запуск обработки</h2>
      <p class="meta">Выберите один или несколько регионов. MegaLoc будет сравнивать
        ФО только с образцами этих регионов и общими индивидуальными конструкциями.</p>
      <div v-if="loading" class="meta">Загрузка регионов…</div>
      <RegionChips v-else v-model="selected" :regions="regions" :disabled="busy"/>
      <div v-if="error" class="alert error" role="alert">{{error}}</div>
      <div class="modal-actions">
        <UiButton :disabled="busy" @click="emit('cancel')">Отмена</UiButton>
        <UiButton kind="primary" :loading="busy" :disabled="loading||!selected.length"
          @click="emit('confirm',selected)">Обработать</UiButton>
      </div>
    </section>
  </div>
</template>
