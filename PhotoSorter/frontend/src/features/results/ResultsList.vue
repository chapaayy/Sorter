<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {usePolling} from '../../composables/usePolling'
import {useDeletionStore} from '../../stores/deletion'
import {resultApi,type PublishedResult} from '../../api/results'
import {date,errorText,runLabels} from '../../utils/format'
import {actualDuration} from '../../utils/queueEstimates'
import PageHeader from '../../components/ui/PageHeader.vue'
import CompactTaskCard from '../../components/ui/CompactTaskCard.vue'
import UiButton from '../../components/ui/UiButton.vue'
import LoadingSkeleton from '../../components/ui/LoadingSkeleton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import {deletionProgress} from '../../utils/deletionProgress'

const deletion=useDeletionStore()
const items=ref<PublishedResult[]>([]),loading=ref(true),paging=ref(false),more=ref(false),error=ref(''),search=ref('')
let revision=0
async function load(append=false,reset=false){
  if(paging.value&&!reset)return
  const request=++revision
  const filter=search.value.trim()
  const existing=append?items.value.length:0
  const target=append||reset?30:Math.max(30,items.value.length)
  if(reset){items.value=[];more.value=false;loading.value=true}
  paging.value=true
  try{
    const next:PublishedResult[]=[]
    let hasMore=true
    do{
      const data=await resultApi.catalog(Math.min(100,target-next.length),existing+next.length,filter)
      if(request!==revision)return
      next.push(...data.items);hasMore=data.has_more&&data.items.length>0
    }while(hasMore&&next.length<target)
    items.value=append?[...items.value,...next]:next
    more.value=hasMore;error.value=''
    deletion.reconcile(items.value.flatMap(item=>item.batch_id&&item.delete_state?
      [{batch_id:item.batch_id,delete_state:item.delete_state}]:[]))
  }catch(e){if(request===revision)error.value=errorText(e)}
  finally{if(request===revision){loading.value=false;paging.value=false}}
}
onMounted(()=>void load())
watch(search,()=>void load(false,true))
usePolling(()=>load(),4000)
const cards=computed(()=>items.value.map(item=>{
  const removal=deletionProgress(item.delete_state,item.deletion_progress,!!item.batch_id&&deletion.pending(item.batch_id))
  const removing=removal.deleting||removal.failed
  const actual=actualDuration(item.actual_started_at||item.started_at,item.actual_finished_at||item.finished_at)
  return {item,removal,progress:removing?removal.percent:item.overall_percent??(item.status==='completed'?100:null),
    stage:removing?removal.stage:item.status==='completed'?'Готово к скачиванию':'Завершено с ошибками',
    time:removing?undefined:actual==='—'?'—':'За '+actual}
}))
</script>
<template>
<PageHeader eyebrow="ГОТОВЫЕ ФОТОГРАФИИ" title="Результаты"/>
<div class="toolbar">
  <input v-model="search" class="search" placeholder="Поиск по названию фотоотчёта…"
    aria-label="Поиск результатов" maxlength="254"/>
  <span class="meta">{{items.length}} завершённых запусков</span>
  <UiButton small @click="load()">Обновить</UiButton>
</div>
<div v-if="error" class="alert error" role="alert">{{error}}</div>
<div v-if="cards.length" class="stack">
  <CompactTaskCard v-for="({item,removal,progress,stage,time},index) in cards" :key="item.id"
    :number="index+1" :title="item.display_name" :thumbnail-url="item.thumbnail_url"
    :status="removal.failed?'Ошибка удаления':removal.deleting?'Удаляется':runLabels[item.status]||item.status"
    :tone="removal.failed?'danger':removal.deleting?'deleting':item.status==='completed'?'success':'warning'"
    :progress="progress" :stage="stage" :indeterminate="removal.inProgress"
    :time-label="time" :time-detail="time?'Фактическая длительность':undefined">
    <template #meta>
      <span v-if="item.photo_count!=null">{{item.photo_count}} фото</span>
      <span v-if="item.groups!=null">{{item.groups}} групп</span>
      <span v-if="item.uncertain!=null">Неопределено: {{item.uncertain}}</span>
      <span>{{date(item.actual_finished_at||item.finished_at)}}</span>
    </template>
    <template #actions>
      <RouterLink v-if="item.can_open!==false" class="task-card-action task-card-action-primary"
        :to="'/results/'+item.id">Открыть</RouterLink>
    </template>
    <template v-if="item.can_zip||item.can_history" #menu>
      <RouterLink v-if="item.can_open!==false" :to="'/results/'+item.id">Просмотреть результаты</RouterLink>
      <a v-if="item.can_zip" :href="resultApi.download(item.id)">Скачать полный ZIP</a>
      <RouterLink v-if="item.can_history" :to="'/queue/runs/'+item.id">История обработки</RouterLink>
    </template>
  </CompactTaskCard>
</div>
<LoadingSkeleton v-else-if="loading" variant="tasks" label="Загружаем результаты"/>
<EmptyState v-else-if="!error" :title="search.trim()?'Ничего не найдено':'Пока нет доступных результатов'"/>
<div v-if="more" class="pagination"><UiButton :loading="paging" @click="load(true)">Показать ещё</UiButton></div>
</template>
