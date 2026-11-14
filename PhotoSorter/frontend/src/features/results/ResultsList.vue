<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {usePolling} from '../../composables/usePolling'
import {useDeletionStore} from '../../stores/deletion'
import {runApi} from '../../api/runs'
import {batchApi} from '../../api/batches'
import {resultApi,type PublishedResult} from '../../api/results'
import type {Run,Batch} from '../../types/api'
import {date,isComplete,errorText,runLabels} from '../../utils/format'
import {runTime} from '../../utils/queueEstimates'
import PageHeader from '../../components/ui/PageHeader.vue'
import CompactTaskCard from '../../components/ui/CompactTaskCard.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import {useSessionStore} from '../../stores/session'

const deletion=useDeletionStore(),session=useSessionStore()
const runs=ref<Run[]>([]),batches=ref<Batch[]>([]),loading=ref(true),error=ref(''),search=ref('')
const published=ref<PublishedResult[]>([]),more=ref(false),paging=ref(false)
const visiblePublished=computed(()=>published.value.filter(item=>item.display_name.toLowerCase().includes(search.value.toLowerCase())))
const batchById=computed(()=>new Map(batches.value.map(b=>[b.batch_id,b])))
const title=(id:string)=>batchById.value.get(id)?.display_name||id
const finished=computed(()=>runs.value.filter(r=>isComplete(r.status)&&
  title(r.batch_id).toLowerCase().includes(search.value.toLowerCase())))
const photoCount=(run:Run)=>run.models?.megaloc?.processed??batchById.value.get(run.batch_id)?.photos
const groups=(run:Run)=>run.models?.megaloc?.groups
const unresolved=(run:Run)=>run.models?.megaloc?.uncertain

async function load(append=false){
  if(!session.isOwner){
    if(paging.value)return
    paging.value=true
    try{
      const data=await resultApi.catalog(30,append?published.value.length:0)
      published.value=append?[...published.value,...data.items]:data.items
      more.value=data.has_more;error.value=''
    }catch(e){error.value=errorText(e)}
    finally{loading.value=false;paging.value=false}
    return
  }
  if(!runs.value.length)loading.value=true
  try{
    const [r,b]=await Promise.all([runApi.list(200),batchApi.list(200)])
    deletion.reconcile(b.batches)
    runs.value=r.runs;batches.value=b.batches;error.value=''
  }catch(e){error.value=errorText(e)}
  finally{loading.value=false}
}
onMounted(()=>{void load()})
usePolling(async()=>{if(session.isOwner)await load()},4000)
const deleting=(batchId:string)=>!deletionFailed(batchId)&&(deletion.pending(batchId)||batchById.value.get(batchId)?.delete_state==='deleting')
const deletionFailed=(batchId:string)=>batchById.value.get(batchId)?.delete_state==='delete_failed'
</script>
<template>
<PageHeader eyebrow="ГОТОВЫЕ ФОТОГРАФИИ" title="Результаты"
  subtitle="Завершённые сортировки, длительность и готовые архивы."/>
<div class="toolbar">
  <input v-model="search" class="search" placeholder="Поиск по названию фотоотчёта…"
    aria-label="Поиск результатов"/>
  <span class="meta">{{session.isOwner?finished.length:visiblePublished.length}} завершённых запусков</span>
  <UiButton small @click="load()">Обновить</UiButton>
</div>
<div v-if="error" class="alert error" role="alert">{{error}}</div>
<template v-if="!session.isOwner">
  <div v-if="visiblePublished.length" class="stack">
    <CompactTaskCard v-for="(item,index) in visiblePublished" :key="item.id" :number="index+1"
      :title="item.display_name" :status="runLabels[item.status]||item.status"
      :tone="item.status==='completed'?'success':'warning'" stage="Готовые фотографии">
      <template #meta><span>{{date(item.finished_at)}}</span></template>
      <template #actions>
        <RouterLink class="task-card-action task-card-action-primary" :to="'/results/'+item.id">Открыть</RouterLink>
      </template>
    </CompactTaskCard>
  </div>
  <EmptyState v-else-if="!loading" title="Доступных результатов нет" detail="Здесь появятся отчёты, к которым администратор открыл доступ."/>
  <div v-else class="meta">Загрузка результатов…</div>
  <div v-if="more" class="pagination"><UiButton :loading="paging" @click="load(true)">Показать ещё</UiButton></div>
</template>
<div v-else-if="finished.length" class="stack">
  <CompactTaskCard v-for="(run,index) in finished" :key="run.id"
    :number="index+1" :title="title(run.batch_id)"
    :thumbnail-url="batchById.get(run.batch_id)?.cover_thumbnail_url"
    :status="deletionFailed(run.batch_id)?'Ошибка удаления':deleting(run.batch_id)?'Удаляется':runLabels[run.status]||run.status"
    :tone="deletionFailed(run.batch_id)?'danger':deleting(run.batch_id)?'deleting':run.status==='completed'?'success':'warning'"
    :progress="run.progress?.overall_percent??(run.status==='completed'?100:null)"
    :stage="deletionFailed(run.batch_id)?'Ошибка удаления':deleting(run.batch_id)?'Удаление файлов и результатов':run.status==='completed'?'Готово к скачиванию':'Завершено с ошибками'"
    :time-label="runTime(run).label" :time-detail="runTime(run).detail">
    <template #meta>
      <span v-if="photoCount(run)!=null">{{photoCount(run)}} фото</span>
      <span v-if="groups(run)!=null">{{groups(run)}} групп</span>
      <span v-if="unresolved(run)!=null">Неопределено: {{unresolved(run)}}</span>
      <span>{{date(run.actual_finished_at||run.finished_at)}}</span>
    </template>
    <template #actions>
      <RouterLink class="task-card-action task-card-action-primary"
        :to="'/results/'+run.id">Открыть</RouterLink>
    </template>
    <template #menu>
      <RouterLink :to="'/results/'+run.id">Просмотреть результаты</RouterLink>
      <a :href="resultApi.download(run.id)">Скачать полный ZIP</a>
      <RouterLink :to="'/queue/runs/'+run.id">История обработки</RouterLink>
    </template>
  </CompactTaskCard>
</div>
<EmptyState v-else-if="!loading" title="Завершённых сортировок нет"
  detail="Загрузите ФО и запустите MegaLoc; результаты появятся здесь." icon="▣">
  <RouterLink class="btn primary" to="/fo">К фотоотчётам</RouterLink>
</EmptyState>
<div v-else class="meta">Загрузка результатов…</div>
</template>
