<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {screenSearchApi} from '../../api/screenSearch'
import {adLayoutApi} from '../../api/adLayouts'
import type {AdRecognition} from '../../api/adLayouts'
import type {ScreenSearchResult,DetectedScreen} from '../../api/screenSearch'
import {errorText} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
const props=withDefaults(defineProps<{runId:string;index:number;imageUrl:string;pinnedLayouts?:boolean}>(),{pinnedLayouts:false})
const emit=defineEmits<{(e:'close'):void}>()
const result=ref<ScreenSearchResult|null>(null),error=ref(''),selected=ref(''),showPoints=ref(false)
const modelReady=ref<boolean|null>(null)
const recognition=ref<AdRecognition|null>(null),recognitionError=ref('')
const dinoReady=ref<boolean|null>(null),ocrReady=ref<boolean|null>(null)
const screen=computed<DetectedScreen|undefined>(()=>result.value?.screens.find(s=>s.screen_id===selected.value))
const corners=computed(()=>screen.value?.corners?.map(p=>p.x+','+p.y).join(' ')||'')
const matches=computed(()=>screen.value?.debug_matches||[])
const sideColor=(side:number)=>['#38bdf8','#34d399','#fbbf24','#c084fc'][side]||'#38bdf8'
async function refresh(){
  try{
    result.value=await screenSearchApi.result(props.runId,props.index)
    selected.value=result.value.screens.find(s=>s.status==='found')?.screen_id||
      result.value.screens[0]?.screen_id||''
    error.value=''
  }catch(e){error.value=errorText(e)}
}
async function loadRecognition(){
  const sid=selected.value
  recognition.value=null;recognitionError.value=''
  if(!sid)return
  try{
    const found=await adLayoutApi.recognized(props.runId,props.index,sid)
    if(selected.value===sid)recognition.value=found
  }catch(e){if(selected.value===sid)recognitionError.value=errorText(e)}
}
watch(selected,()=>{void loadRecognition()})
onMounted(()=>{
  void refresh()
  void screenSearchApi.model().then(info=>{modelReady.value=info.available}).catch(()=>{})
  void adLayoutApi.models().then(info=>{dinoReady.value=info.dino.available;ocrReady.value=info.ocr.available}).catch(()=>{})
})
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
          <p v-if="modelReady===false" class="meta">XFeat не установлена или контрольная сумма файлов не совпала.
            Сначала установите проверенные веса через <code>docker compose exec api python -m app.screen_detection.cli --install</code>.</p>
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
            :kind="selected===item.screen_id?'primary':'secondary'"
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
              :r="Math.max(2,result.image_width*.002)"  :fill="sideColor(pair.side)"/>
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
          <div v-if="showPoints&&matches.length&&screen.reference_width&&screen.reference_height"
            class="screen-search-reference">
            <div class="row between wrap">
              <strong>Совпавшие признаки на Образце</strong>
              <span class="meta">Те же цвета сторон, что и на ФО · {{matches.length}} подтверждённых точек</span>
            </div>
            <div class="screen-search-ref-picture">
              <img :src="'/api/photos/'+encodeURIComponent(screen.reference_id)+'/original'"
                alt="Образец с исходными точками XFeat"/>
              <svg :viewBox="'0 0 '+screen.reference_width+' '+screen.reference_height"
                preserveAspectRatio="xMidYMid meet" aria-label="Опорные точки Образца">
                <circle v-for="(pair,i) in matches" :key="i"
                  :cx="pair.reference[0]" :cy="pair.reference[1]"
                  :r="Math.max(2,screen.reference_width*.002)"
                  :fill="sideColor(pair.side)"/>
              </svg>
            </div>
          </div>
          <div v-if="screen.status==='found'&&screen.corners?.length" class="meta">
            Координаты: {{screen.corners.map(p=>Math.round(p.x)+','+Math.round(p.y)).join(' · ')}}
          </div>
          <div v-if="screen.status==='found'" class="ad-recognition-detail">
            <div class="row between wrap">
              <strong>DINOv2 · распознавание рекламы</strong>
              <RouterLink class="meta" to="/layouts" @click="emit('close')">Библиотека макетов</RouterLink>
            </div>
            <div v-if="recognitionError" class="alert error">{{recognitionError}}</div>
            <template v-if="recognition">
              <p v-if="recognition.status==='not_processed'" class="meta">
                Ещё не выполнено. Запустите после XFeat:
                <code>docker compose exec worker python -m app.ad_recognition.cli --run-id {{runId}} --limit 20</code>
                <span v-if="dinoReady===false">. Сначала установите веса DINOv2 командой
                  <code>docker compose exec api python -m app.ad_recognition.cli --install-dino</code></span>
              </p>
              <template v-else>
                <div class="row between wrap">
                  <strong>{{recognition.status==='matched'?'Макет DINOv2 выбран':
                    recognition.status==='uncertain'?'DINOv2: требуется проверка':
                    recognition.status==='no_match'?'Макет не определён':'Реклама не распознана'}}</strong>
                  <span class="meta">{{recognition.elapsed_seconds??'—'}} с</span>
                </div>
                <p class="meta">{{recognition.reason}}</p>
                <div v-if="recognition.quality" class="stack-sm">
                  <div class="row between wrap">
                    <strong>Качество видимости рекламы</strong>
                    <strong v-if="recognition.quality.status==='measured'">
                      {{recognition.quality.score.toFixed(1)}} / 100
                    </strong>
                  </div>
                  <div v-if="recognition.quality.metrics" class="row wrap screen-search-metrics">
                    <span>Резкость: {{Math.round(recognition.quality.metrics.sharpness*100)}}%</span>
                    <span>Экспозиция: {{Math.round(recognition.quality.metrics.exposure*100)}}%</span>
                    <span>Без бликов: {{Math.round(recognition.quality.metrics.glare*100)}}%</span>
                    <span>Видимость экрана: {{Math.round(recognition.quality.metrics.screen_coverage*100)}}%</span>
                  </div>
                  <p v-if="recognition.best_for_layout" class="meta">
                    Выбрана лучшей ФО для этого макета и физического экрана.
                  </p>
                  <p class="meta">Оценка относительная, не вероятность распознавания.</p>
                </div>
                <div v-if="recognition.top?.length" class="ad-recognition-preview">
                  <img :src="pinnedLayouts?'/api/ad-results/runs/'+encodeURIComponent(runId)+'/layouts/'+recognition.top[0].id+'/image':
                    '/api/ad-layouts/'+recognition.top[0].id+'/image'"
                    :alt="recognition.top[0].name"/>
                  <div class="stack-sm">
                    <strong>{{recognition.top[0].name}}</strong>
                    <p class="meta">Сходство DINOv2: {{recognition.top[0].score.toFixed(3)}}
                      · Разница с №2: {{recognition.margin==null?'—':recognition.margin.toFixed(3)}}</p>
                    <div class="ad-recognition-top">
                      <div v-for="(match,i) in recognition.top.slice(0,5)" :key="match.id" class="row between">
                        <span>{{i+1}}. {{match.name}}</span><b>{{match.score.toFixed(3)}}</b>
                      </div>
                    </div>
                    <RouterLink v-if="recognition.visual_group_id" class="meta"
                      :to="{path:'/results/'+runId,query:{view:'comparisons',group:recognition.visual_group_id}}"
                      @click="emit('close')">Все {{recognition.top.length}} сравнений и полные оценки DINOv2</RouterLink>
                  </div>
                </div>
                <div v-if="recognition.ocr" class="stack-sm">
                  <strong>PP-OCRv5 · {{recognition.ocr.status==='confirmed'?'Текст подтверждён':
                    recognition.ocr.status==='mismatch'?'Текст не совпал':
                    recognition.ocr.status==='unreadable'?'Текст не прочитан':
                    recognition.ocr.status==='unavailable'?'OCR не установлен':
                    recognition.ocr.status==='not_configured'?'Контрольный текст отсутствует':'Дополнительная проверка'}}</strong>
                  <div class="meta">{{recognition.ocr.reason}}
                    <span v-if="recognition.ocr.matched_terms!=null">
                      · {{recognition.ocr.matched_terms}} / {{recognition.ocr.total_terms}} из прочитанных слов ФО
                    </span>
                  </div>
                  <div v-if="recognition.ocr.lines?.length" class="meta">
                    Прочитано: {{recognition.ocr.lines.join(' · ')}}
                  </div>
                  <div v-for="(issue,i) in recognition.ocr.contradictions||[]" :key="'hard'+i" class="meta">
                    Расхождение ({{issue.kind==='dates'?'дата':issue.kind==='prices'?'цена':
                      issue.kind==='percentages'?'процент':'число'}}):
                    в макете {{issue.expected.join(', ')}} · на ФО {{issue.observed.join(', ')}}
                  </div>
                  <div v-for="(issue,i) in recognition.ocr.possible_contradictions||[]" :key="'weak'+i" class="meta">
                    {{recognition.ocr.contradictions?.some(item=>item.kind===issue.kind)?'Подтверждённое':'Возможное'}}
                    расхождение ({{issue.kind==='dates'?'дата':issue.kind==='prices'?'цена':
                      issue.kind==='percentages'?'процент':'число'}}):
                    в макете {{issue.expected.join(', ')}} · на ФО {{issue.observed.join(', ')}}
                  </div>
                  <p v-if="ocrReady===false" class="meta">
                    Для OCR установите модели через
                    <code>docker compose exec api python -m app.ad_recognition.cli --install-ocr</code>.
                  </p>
                </div>
                <p v-if="recognition.review_required" class="meta">
                  Требуется ручная проверка. OCR не менял кандидата DINOv2.
                </p>
              </template>
            </template>
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
