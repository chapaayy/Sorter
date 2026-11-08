<script setup lang="ts">
import {ref,watch} from 'vue'
import {workQueueApi} from '../../api/workQueue'
import type {PreparationDetail,LayoutPreparationDetail} from '../../types/workQueue'
import {errorText,date} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'

const props=defineProps<{jobId:string;kind:'reference_preparation'|'layout_preparation'}>()
const emit=defineEmits<{(e:'close'):void}>()
const detail=ref<PreparationDetail|null>(null)
const layoutDetail=ref<LayoutPreparationDetail|null>(null),error=ref('')
async function refresh(){
  try{
    if(props.kind==='layout_preparation'){
      layoutDetail.value=await workQueueApi.layoutPreparation(props.jobId);detail.value=null
    }else{
      detail.value=await workQueueApi.preparation(props.jobId);layoutDetail.value=null
    }
    error.value=''
  }
  catch(e){error.value=errorText(e)}
}
watch(()=>[props.jobId,props.kind],()=>void refresh(),{immediate:true})
</script>
<template>
<section class="panel stack" aria-label="Детали подготовки">
  <div class="row between wrap">
    <h2 style="margin:0">{{props.kind==='layout_preparation'?'Подготовка рекламы':'Подготовка образцов'}}</h2>
    <div class="row wrap">
      <UiButton small @click="refresh">Обновить</UiButton>
      <UiButton small @click="emit('close')">Закрыть</UiButton>
    </div>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <template v-if="layoutDetail">
    <div class="meta">{{layoutDetail.layout_name||'Макет рекламы'}}
      · задание #{{layoutDetail.queue_seq}}
      · {{layoutDetail.state}} · {{layoutDetail.progress_stage}}
      · {{layoutDetail.progress_percent}}%</div>
    <progress :value="layoutDetail.progress_percent" max="100" style="width:100%"/>
    <p v-if="layoutDetail.error" class="alert error" role="alert">{{layoutDetail.error}}</p>
  </template>
  <template v-if="detail">
    <div class="meta">Задание #{{detail.queue_seq}} · {{detail.state}} · этап: {{detail.progress_stage||'—'}}
      · готово {{detail.completed_count}}/{{detail.total_count}} · ошибок {{detail.failed_count}}</div>
    <p v-if="detail.error" class="alert error" role="alert">{{detail.error}}</p>
    <div v-if="detail.errors.length" class="stack-sm">
      <strong>Ошибки файлов</strong>
      <div v-for="item in detail.errors" :key="item.upload_id" class="meta"
        style="padding:8px 0;border-bottom:1px solid var(--border-subtle);overflow-wrap:anywhere">
        {{date(item.occurred_at)}} · {{item.upload_id}} · {{item.detail}}
      </div>
    </div>
    <div v-else class="meta">Ошибок отдельных файлов не зафиксировано.</div>
  </template>
</section>
</template>
