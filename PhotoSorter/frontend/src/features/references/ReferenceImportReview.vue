<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import UiButton from '../../components/ui/UiButton.vue'
import type {ReferenceReview} from '../../types/referenceTransfer'
import {bytes,errorText} from '../../utils/format'
import {referenceImportsApi} from '../../api/referenceImports'

const props=defineProps<{review:ReferenceReview;beforeConfirm?:()=>Promise<void>}>()
const emit=defineEmits<{(e:'confirm',updated:number):void;(e:'cancel'):void;(e:'checking',busy:boolean):void}>()
const selected=ref<string[]>([]),busy=ref(false),error=ref('')
const conflicts=computed(()=>props.review.sideConflicts||[])
function selectAll(){selected.value=conflicts.value.map(c=>c.reference_id)}
async function confirm(){
  if(busy.value)return
  const changes=conflicts.value.filter(c=>selected.value.includes(c.reference_id)).map(c=>({
    reference_id:c.reference_id,sam:c.file.sam,sha256:c.file.sha256,size:c.file.entry.file.size,
    existing_side:c.existing_side,requested_side:c.requested_side,...(c.file.portable?{portable:true}:{})
  }))
  if(!changes.length&&!props.beforeConfirm){emit('confirm',0);return}
  busy.value=true;error.value='';emit('checking',true)
  try{
    if(props.beforeConfirm)await props.beforeConfirm()
    const result=changes.length?await referenceImportsApi.resolveSides(changes):{confirmed:0}
    if(result.confirmed!==changes.length)throw new Error('Неполное подтверждение изменения сторон')
    emit('confirm',result.confirmed)
  }catch(e){error.value=errorText(e)}
  finally{busy.value=false;emit('checking',false)}
}
const heading=ref<HTMLElement|null>(null)
onMounted(()=>heading.value?.focus())
</script>

<template>
  <section class="stack reference-review" aria-label="Результат проверки образцов">
    <h3 ref="heading" tabindex="-1">Проверка на дубли завершена</h3>
    <p v-if="conflicts.length">Стороны существующих фото сохраняются, пока вы явно не выберете изменения. Фото повторно не загружаются.</p>
    <p v-else-if="!review.newFiles.length">Все выбранные фото уже есть в библиотеке. Загрузки не будет, в очередь ничего не добавится.</p>
    <p v-else-if="review.duplicates.length">Дубли не будут загружены. Нажмите «ОК», чтобы загрузить только новые фото.</p>
    <p v-else>Дублей нет. Нажмите «ОК», чтобы начать загрузку.</p>
    <details v-if="conflicts.length" open>
      <summary>Конфликты сторон — {{conflicts.length}}</summary>
      <p class="meta">Отметьте фото, для которых нужно принять сторону из папки. Остальные сохранят текущую сторону.</p>
      <div class="row wrap">
        <UiButton small :disabled="busy" @click="selectAll">Принять все стороны</UiButton>
        <UiButton small :disabled="busy" @click="selected=[]">Сохранить все текущие</UiButton>
      </div>
      <ul class="review-list">
        <li v-for="conflict in conflicts" :key="conflict.reference_id">
          <label class="row wrap">
            <input type="checkbox" v-model="selected" :value="conflict.reference_id" :disabled="busy"/>
            <span>{{conflict.file.entry.relative}} · {{conflict.existing_side||'Без стороны'}} → {{conflict.requested_side}}</span>
          </label>
        </li>
      </ul>
      <p class="meta">Будет изменено: {{selected.length}}. Изменения применяются сразу после ОК, перед загрузкой новых фото.</p>
    </details>
    <div v-if="error" class="alert error" role="alert">{{error}}</div>
    <details :open="!!review.duplicates.length">
      <summary>Дубли — {{review.duplicates.length}}</summary>
      <ul v-if="review.duplicates.length" class="review-list">
        <li v-for="(file,i) in review.duplicates" :key="i">
          <span>{{file.entry.relative}}</span>
          <span class="meta">{{file.sam}} · {{file.reason==='library'?'Уже в библиотеке':'Повтор среди выбранных фото'}}</span>
        </li>
      </ul>
      <p v-else class="meta">Совпадений не найдено.</p>
    </details>
    <details :open="!!review.newFiles.length">
      <summary>Новые фото — {{review.newFiles.length}}<template v-if="review.newFiles.length"> · {{bytes(review.totalBytes)}}</template></summary>
      <ul v-if="review.newFiles.length" class="review-list">
        <li v-for="(file,i) in review.newFiles" :key="i">
          <span>{{file.entry.relative}}</span>
          <span class="meta">{{file.sam}} · {{file.side?'Сторона '+file.side:'Без стороны'}}</span>
        </li>
      </ul>
      <p v-else class="meta">Новых фото нет.</p>
    </details>
    <div class="modal-actions">
      <UiButton :disabled="busy" @click="emit('cancel')">Отмена</UiButton>
      <UiButton kind="primary" :loading="busy" @click="confirm">ОК</UiButton>
    </div>
  </section>
</template>

<style scoped>
.reference-review h3,.reference-review p{margin:0}
.reference-review details{padding:10px 12px;background:var(--panel-alt);border:1px solid var(--border-subtle);border-radius:8px}
.reference-review details p{margin-top:8px}
.reference-review summary{cursor:pointer;font-weight:600}
.review-list{list-style:none;padding:0;margin:8px 0 0;max-height:min(18vh,160px);overflow:auto}
.review-list li{display:grid;gap:3px;padding:6px 0;border-top:1px solid var(--border-subtle);overflow-wrap:anywhere}
</style>
