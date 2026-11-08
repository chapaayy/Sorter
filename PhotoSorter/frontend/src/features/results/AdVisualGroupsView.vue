<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {adResultsApi} from '../../api/adResults'
import type {VisualGroup,VisualGroupsPage} from '../../api/adResults'
import {screenSearchApi} from '../../api/screenSearch'
import {errorText} from '../../utils/format'
import GroupPicker from '../../components/split/GroupPicker.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'

const props=defineProps<{runId:string}>()
const emit=defineEmits<{(e:'inspect',index:number):void}>()
const route=useRoute(),router=useRouter()
const groups=ref<VisualGroup[]>([]),current=ref(''),detail=ref<VisualGroup|null>(null)
const total=ref(0),threshold=ref<number|null>(null),status=ref('loading')
const busy=ref(false),detailBusy=ref(false),error=ref(''),limitShown=ref(32)
const entries=computed(()=>groups.value.map(group=>({
  id:group.id,label:group.id+' · '+group.assigned_sam+' · '+(group.screen_id.slice(0,8)),
  count:group.member_count
})))
const members=computed(()=>detail.value?.members?.slice(0,limitShown.value)||[])
const format=(value:number|null|undefined)=>value==null?'—':value.toFixed(4)

async function loadMore(){
  if(busy.value)return
  busy.value=true
  try{
    const page:VisualGroupsPage=await adResultsApi.visualGroups(props.runId,50,groups.value.length)
    groups.value.push(...page.groups)
    total.value=page.total;threshold.value=page.grouping_threshold??null
    status.value=page.status;error.value=''
    if(!current.value&&groups.value.length)current.value=String(route.query.group||groups.value[0].id)
  }catch(e){error.value=errorText(e)}
  finally{busy.value=false}
}
watch(current,async id=>{
  detail.value=null;limitShown.value=32
  if(!id)return
  detailBusy.value=true
  try{
    const loaded=await adResultsApi.visualGroup(props.runId,id)
    if(current.value===id){detail.value=loaded;error.value=''}
  }catch(e){if(current.value===id)error.value=errorText(e)}
  finally{if(current.value===id)detailBusy.value=false}
})
onMounted(()=>{void loadMore()})
function compare(group:string){
  void router.push({path:route.path,query:{...route.query,view:'comparisons',group}})
}
</script>
<template>
<section class="stack result-ad-view">
  <div class="row between wrap">
    <div><h2>По рекламе (группы) · DINOv2</h2>
      <p class="meta">Исходная визуальная группировка до выбора рекламного макета и проверки текста.</p></div>
    <span class="meta">Порог cosine: {{format(threshold)}} · Групп: {{total}}</span>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <div v-if="groups.length" class="split">
    <div class="stack" style="min-width:0">
      <GroupPicker v-model="current" :items="entries" placeholder="Поиск R0001 или SAM…"/>
      <UiButton v-if="groups.length<total" small :loading="busy" @click="loadMore">Ещё группы · {{groups.length}} / {{total}}</UiButton>
    </div>
    <section class="panel split-main stack">
      <p v-if="detailBusy" class="meta">Загрузка сохранённой группы…</p>
      <template v-if="detail">
        <div class="row between wrap">
          <div><h2>{{detail.id}} · {{detail.assigned_sam}}</h2>
            <p class="meta">Физический экран {{detail.screen_id}} · {{detail.member_count}} ФО</p></div>
          <UiButton small @click="compare(detail.id)">Сравнения DINOv2</UiButton>
        </div>
        <div class="result-ad-metrics">
          <span>Минимальное сходство: <strong>{{format(detail.min_pairwise_similarity)}}</strong></span>
          <span>Среднее сходство: <strong>{{format(detail.mean_pairwise_similarity)}}</strong></span>
          <span>Ближайшая другая группа: <strong>{{detail.nearest_other_group||'—'}}</strong></span>
          <span>Сходство с ней: <strong>{{format(detail.nearest_other_similarity)}}</strong></span>
          <span>Порог: <strong>{{format(detail.threshold)}}</strong></span>
        </div>
        <p class="meta">{{detail.formation_reason}}</p>
        <p class="meta">{{detail.separation_reason}}</p>
        <div v-if="detail.match?.status" class="row between wrap">
          <span class="status" :class="detail.match.status==='matched'?'ok':''">
            Сопоставление: {{detail.match.status}}
          </span>
          <span v-if="'best_score' in detail.match" class="meta">
            Лучший cosine: {{format(detail.match.best_score)}}
          </span>
        </div>
        <div class="result-ad-member-grid">
          <article v-for="member in members" :key="member.index+':'+member.screen_id" class="result-ad-photo">
            <img :src="screenSearchApi.crop(runId,member.index,member.screen_id)"
              :alt="'Экран ФО '+(member.index+1)" loading="lazy"/>
            <div class="stack-sm">
              <strong>ФО №{{member.index+1}}</strong>
              <span v-if="member.joined_via" class="meta">
                Объединена через ФО №{{member.joined_via.index+1}} · {{format(member.joined_via.similarity)}}
              </span>
              <span v-else class="meta">Начало связной группы</span>
              <span v-if="member.nearest_peers?.length" class="meta">
                Ближайшая ФО №{{member.nearest_peers[0].index+1}} · {{format(member.nearest_peers[0].similarity)}}
              </span>
              <span v-if="member.nearest_separate" class="meta">
                Вне группы: ФО №{{member.nearest_separate.index+1}} · {{format(member.nearest_separate.similarity)}}
              </span>
              <UiButton small @click="emit('inspect',member.index)">Исходная ФО / XFeat</UiButton>
            </div>
          </article>
        </div>
        <UiButton v-if="(detail.members?.length||0)>limitShown" small @click="limitShown+=32">
          Показать ещё участников
        </UiButton>
      </template>
    </section>
  </div>
  <EmptyState v-else-if="!busy&&status==='not_processed'" title="DINOv2 ещё не обработан"
    detail="В этой сортировке нет сохранённых рекламных групп."/>
  <EmptyState v-else-if="!busy&&!groups.length" title="Рекламных групп нет"
    detail="XFeat не подтвердил экраны либо DINOv2 не получил ни одного пригодного фрагмента."/>
</section>
</template>
