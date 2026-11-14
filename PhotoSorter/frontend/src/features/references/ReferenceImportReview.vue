<script setup lang="ts">
import {onMounted,ref} from 'vue'
import UiButton from '../../components/ui/UiButton.vue'
import type {ReferenceReview} from '../../types/referenceTransfer'
import {bytes} from '../../utils/format'

defineProps<{review:ReferenceReview}>()
const emit=defineEmits<{(e:'confirm'):void;(e:'cancel'):void}>()
const heading=ref<HTMLElement|null>(null)
onMounted(()=>heading.value?.focus())
</script>

<template>
  <section class="stack reference-review" aria-label="Результат проверки образцов">
    <h3 ref="heading" tabindex="-1">Проверка на дубли завершена</h3>
    <p v-if="!review.newFiles.length">Все выбранные фото уже есть в библиотеке. Загрузки не будет, в очередь ничего не добавится.</p>
    <p v-else-if="review.duplicates.length">Дубли не будут загружены. Нажмите «ОК», чтобы загрузить только новые фото.</p>
    <p v-else>Дублей нет. Нажмите «ОК», чтобы начать загрузку.</p>
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
          <span class="meta">{{file.sam}}</span>
        </li>
      </ul>
      <p v-else class="meta">Новых фото нет.</p>
    </details>
    <div class="modal-actions">
      <UiButton @click="emit('cancel')">Отмена</UiButton>
      <UiButton kind="primary" @click="emit('confirm')">ОК</UiButton>
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
