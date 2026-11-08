<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {screenSearchApi} from '../../api/screenSearch'
import type {ScreenSearchResult,DetectedScreen} from '../../api/screenSearch'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
const props=defineProps<{runId:string;index:number;imageUrl:string}>()
const emit=defineEmits<{(e:'close'):void}>()
const result=ref<ScreenSearchResult|null>(null),error=ref(''),selected=ref(''),showPoints=ref(false)
const screen=computed<DetectedScreen|undefined>(()=>result.value?.screens.find(s=>s.screen_id===selected.value))
const corners=computed(()=>screen.value?.corners?.map(p=>p.x+','+p.y).join(' ')||'')
const matches=computed(()=>screen.value?.debug_matches||[])
async function refresh(){
  try{
    result.value=await screenSearchApi.result(props.runId,props.index)
    selected.value=result.value.screens.find(s=>s.status==='found')?.screen_id||
      result.value.screens[0]?.screen_id||''
    error.value=''
  }catch(e){error.value=errorText(e)}
}
onMounted(()=>{void refresh()})
</script>
<template>
<Teleport to="body">
  <div class="modal-overlay screen-editor-overlay" @click.self="emit('close')">
    <section class="modal screen-search-dialog" role="dialog" aria-modal="true" aria-label="Диагностика XFeat">
      <div class="row between wrap">
        <div><h2>Поиск экрана · XFeat</h2><p class="meta">ФО №{{index+1}} · {{result?.assigned_sam||'Конструкция неизвестна'}}</p></div>
        <UiButton @click="emit('close')">Закрыть</UiButton>
      </div>
      <div v-if="error" class="alert error" role="alert">{{error}}</div>
      <template v-if="result">
        <div v-if="result.status==='not_processed'" class="alert">
          Анализ этой ФО ещё не запущен. На новом VPS выполните команду
          <code>docker compose exec worker python -m app.screen_detection.cli --run-id {{runId}}</code>.
          ZIP и результаты MegaLoc при этом не изменяются.
        </div>
        <div v-else class="row between wrap">
          <strong>{{result.status==='found'?'Экран найден':result.status==='error'?'Ошибка обработки':'Экран не найден'}}</strong>
          <span class="meta">{{result.reason}} · {{result.elapsed_seconds??'—'}} с</span>
        </div>
        <div v-if="result.screens.length>1" class="row wrap">
          <UiButton v-for="item in result.screens" :key="item.screen_id" small
            :kind="selected===item.screen_id?'primary':'default'"
            @click="selected=item.screen_id">{{item.screen_name}}</UiButton>
        </div>
        <div v-if="result.status!=='not_processed'" class="screen-search-stage">
          <img :src="imageUrl" alt="Исходная ФО"/>
          <svg v-if="result.image_width&&result.image_height"
            :viewBox="'0 0 '+result.image_width+' '+result.image_height"
            preserveAspectRatio="xMidYMid meet" aria-label="Найденный контур экрана">
            <polygon v-if="screen?.status==='found'" :points="corners" fill="rgba(16,185,129,.12)"
              stroke="#34d399" :stroke-width="Math.max(3,result.image_width*.002)"/>
            <circle v-for="(p,i) in screen?.corners||[]" :key="i"
              :cx="p.x" :cy="p.y" :r="Math.max(5,result.image_width*.004)"
              fill="#fff" stroke="#047857" :stroke-width="3"/>
            <circle v-if="showPoints" v-for="(pair,i) in matches" :key="'m'+i"
              :cx="pair.photo[0]" :cy="pair.photo[1]"
              :r="Math.max(2,result.image_width*.002)" fill="#38bdf8"/>
          </svg>
        </div>
        <div v-if="screen" class="stack-sm">
          <div class="row between wrap">
            <strong>{{screen.screen_name}} · {{screen.status==='found'?'Найден':'Не найден'}}</strong>
            <span class="meta">Разметка v{{screen.annotation_version}}</span>
          </div>
          <div class="meta">{{screen.reason}}</div>
          <div class="row wrap screen-search-metrics">
            <span>Совпадения: {{screen.matches??0}}</span>
            <span>Подтверждены: {{screen.inliers??0}}</span>
            <span>Стороны: {{screen.supported_sides?.length??0}}/4</span>
            <span>Ошибка: {{screen.reprojection_error_px??'—'}} px</span>
            <label v-if="matches.length" class="row"><input v-model="showPoints" type="checkbox"/> Показать точки</label>
          </div>
          <div v-if="screen.status==='found'&&screen.corners?.length" class="meta">
            Координаты: {{screen.corners.map(p=>Math.round(p.x)+','+Math.round(p.y)).join(' · ')}}
          </div>
          <div v-if="screen.status==='found'" class="screen-search-crop">
            <div><strong>Оригинальный вырезанный фрагмент</strong>
              <p class="meta">Без перспективного выравнивания и дорисовки пикселей</p></div>
            <img :src="screenSearchApi.crop(runId,index,screen.screen_id)" :alt="'Фрагмент '+screen.screen_name"/>
          </div>
        </div>
      </template>
    </section>
  </div>
</Teleport>
</template>
