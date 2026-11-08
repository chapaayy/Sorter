<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import {adResultsApi} from '../../api/adResults'
import type {OcrRecognition,RankedLayout,RankingsPage,VisualGroup} from '../../api/adResults'
import {screenSearchApi} from '../../api/screenSearch'
import {errorText} from '../../utils/format'
import GroupPicker from '../../components/split/GroupPicker.vue'
import UiButton from '../../components/ui/UiButton.vue'
import EmptyState from '../../components/ui/EmptyState.vue'
import AdTextEvidence from './AdTextEvidence.vue'

const props=defineProps<{runId:string}>()
const emit=defineEmits<{(e:'inspect',index:number):void}>()
const route=useRoute(),router=useRouter()
const groups=ref<VisualGroup[]>([]),totalGroups=ref(0),selectedGroup=ref('')
const detail=ref<VisualGroup|null>(null),memberKey=ref('')
const rankings=ref<RankedLayout[]>([]),rankTotal=ref(0),rankMeta=ref<RankingsPage|null>(null)
const evidence=ref<OcrRecognition|null>(null),busy=ref(false),rankBusy=ref(false),error=ref('')
const groupChoices=computed(()=>groups.value.map(group=>({
 id:group.id,label:group.id+' · '+group.assigned_sam+' · '+group.screen_id.slice(0,8),
 count:group.member_count
})))
const member=computed(()=>detail.value?.members?.find(
  item=>memberKey.value===item.index+':'+item.screen_id))
const format=(v:number|null|undefined)=>v==null?'—':v.toFixed(6)
let generation=0

async function moreGroups(){
  if(busy.value)return
  busy.value=true
  try{
    const response=await adResultsApi.visualGroups(props.runId,50,groups.value.length)
    groups.value.push(...response.groups);totalGroups.value=response.total
    if(!selectedGroup.value&&groups.value.length){
      selectedGroup.value=typeof route.query.group==='string'?route.query.group:groups.value[0].id
    }
    error.value=''
  }catch(e){error.value=errorText(e)}
  finally{busy.value=false}
}
async function fetchRankings(reset=false){
  if(!selectedGroup.value)return
  if(reset){generation++;rankings.value=[];rankTotal.value=0;rankMeta.value=null}
  else if(rankBusy.value)return
  const current=generation
  const gid=selectedGroup.value,key=memberKey.value
  const index=key?Number(key.split(':')[0]):undefined
  const sid=key?key.substring(key.indexOf(':')+1):undefined
  rankBusy.value=true
  try{
    const response=await adResultsApi.rankings(props.runId,gid,{
      limit:30,offset:rankings.value.length,index,screen_id:sid
    })
    if(generation===current&&selectedGroup.value===gid&&memberKey.value===key){
      rankings.value.push(...response.rankings)
      rankTotal.value=response.total;rankMeta.value=response;error.value=''
    }
  }catch(e){if(generation===current)error.value=errorText(e)}
  finally{if(generation===current)rankBusy.value=false}
}
watch(selectedGroup,async gid=>{
  generation++;detail.value=null;memberKey.value='';rankings.value=[];rankMeta.value=null;evidence.value=null
  if(!gid)return
  const current=gid
  void router.replace({path:route.path,query:{...route.query,view:'comparisons',group:gid}})
  try{
    const item=await adResultsApi.visualGroup(props.runId,gid)
    if(selectedGroup.value===current){
      detail.value=item
      void fetchRankings(true)
    }
  }catch(e){if(selectedGroup.value===current)error.value=errorText(e)}
})
watch(memberKey,async key=>{
  evidence.value=null
  void fetchRankings(true)
  if(!key||!member.value)return
  const currentGroup=selectedGroup.value
  try{
    const item=await adResultsApi.recognition(props.runId,member.value.index,member.value.screen_id)
    if(selectedGroup.value===currentGroup&&memberKey.value===key)evidence.value=item
  }catch(e){if(selectedGroup.value===currentGroup&&memberKey.value===key)error.value=errorText(e)}
})
onMounted(()=>{void moreGroups()})
</script>
<template>
<section class="stack result-ad-view">
  <div class="row between wrap">
    <div><h2>Сравнения · DINOv2</h2>
      <p class="meta">Все закреплённые макеты, реальные cosine, вклад каждой ФО, пороги и независимая проверка OCR.</p></div>
    <span class="meta">{{totalGroups}} визуальных групп</span>
  </div>
  <div v-if="error" class="alert error" role="alert">{{error}}</div>
  <div v-if="groups.length||selectedGroup" class="split">
    <div class="stack">
      <GroupPicker v-model="selectedGroup" :items="groupChoices" placeholder="Найти R0001…"/>
      <UiButton v-if="groups.length<totalGroups" small :loading="busy" @click="moreGroups">
        Ещё группы · {{groups.length}} / {{totalGroups}}
      </UiButton>
    </div>
    <section class="panel split-main stack">
      <template v-if="detail">
        <div class="row between wrap">
          <div><h2>{{detail.id}} · {{detail.assigned_sam}}</h2>
            <p class="meta">Физический экран {{detail.screen_id}} · {{detail.member_count}} участников</p></div>
          <span class="status" :class="rankMeta?.status==='matched'?'ok':''">{{rankMeta?.status||'Ожидание сопоставления'}}</span>
        </div>
        <div class="field">
          <label class="label" for="ad-compare-member">Уровень сравнения</label>
          <select id="ad-compare-member" v-model="memberKey">
            <option value="">Вся визуальная группа · среднее cosine по всем ФО</option>
            <option v-for="item in detail.members||[]" :key="item.index+':'+item.screen_id"
              :value="item.index+':'+item.screen_id">
              ФО №{{item.index+1}} · {{item.screen_name||'экран'}}
            </option>
          </select>
        </div>
        <div class="result-ad-metrics">
          <span>Порог принятия: <strong>{{format(rankMeta?.matching_threshold)}}</strong></span>
          <span>1-й vs 2-й: <strong>{{format(memberKey?rankMeta?.member_margin:rankMeta?.margin)}}</strong></span>
          <span>Лучший групповой cosine: <strong>{{format(rankMeta?.best_score)}}</strong></span>
          <span>Кандидатов: <strong>{{rankTotal}}</strong></span>
          <span>Метод: {{rankMeta?.method||'—'}}</span>
        </div>
        <p class="meta">{{rankMeta?.reason||detail.match?.reason||'Результат сравнения отсутствует'}}</p>
        <p class="meta">Макет выбирается только по DINOv2. OCR не изменяет выбор кандидата.</p>
        <div v-if="rankings.length" class="result-rank-table-wrap">
          <table class="result-rank-table">
            <thead><tr><th>№</th><th>Рекламный макет</th><th>Группа · cosine</th>
              <th v-if="memberKey">Выбранная ФО · cosine</th>
              <th>Мин / Макс по группе</th><th>Результат</th></tr></thead>
            <tbody>
              <tr v-for="(item,i) in rankings" :key="item.id">
                <td>{{i+1+(rankTotal?((rankMeta?.offset)||0):0)}}</td>
                <td>
                  <div class="row result-rank-layout">
                    <img :src="adResultsApi.layoutImage(runId,item.id)" :alt="item.name" loading="lazy"/>
                    <div class="stack-sm"><strong>{{item.name}}</strong><span class="meta">v{{item.version}}</span></div>
                  </div>
                </td>
                <td><strong>{{format(item.score)}}</strong></td>
                <td v-if="memberKey">{{format(item.member_score)}}</td>
                <td>{{format(item.minimum_member_score)}} / {{format(item.maximum_member_score)}}</td>
                <td>
                  <span v-if="item.id===rankMeta?.candidate_id" class="status ok">Выбран</span>
                  <span v-else-if="item.score<(rankMeta?.matching_threshold??0)" class="meta">Ниже порога</span>
                  <span v-else class="meta">Альтернатива</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else-if="!rankBusy" class="meta">У этой группы пока нет сохранённого сравнения с макетами.</p>
        <div v-if="rankings.length<rankTotal" class="row" style="justify-content:center">
          <UiButton small :loading="rankBusy" @click="fetchRankings()">Ещё кандидаты · {{rankings.length}} / {{rankTotal}}</UiButton>
        </div>
        <section v-if="member" class="stack-sm result-compare-evidence">
          <div class="row between wrap">
            <h3>Экран ФО №{{member.index+1}} · OCR</h3>
            <UiButton small @click="emit('inspect',member.index)">Геометрия XFeat</UiButton>
          </div>
          <img :src="screenSearchApi.crop(runId,member.index,member.screen_id)" :alt="'Экран ФО '+(member.index+1)" loading="lazy"/>
          <AdTextEvidence v-if="evidence" :recognition="evidence"/>
          <p v-else class="meta">Текстовые результаты для выбранного кадра недоступны.</p>
        </section>
      </template>
      <p v-else class="meta">Выберите визуальную группу для просмотра полных сохранённых сравнений.</p>
    </section>
  </div>
  <EmptyState v-else-if="!busy" title="Сравнения не опубликованы"
    detail="Нет сохранённых визуальных групп DINOv2. Откройте завершённую обработку рекламы."/>
</section>
</template>
