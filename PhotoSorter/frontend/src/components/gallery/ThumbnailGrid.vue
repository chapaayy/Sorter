<script setup lang="ts">
import DeferredImage from './DeferredImage.vue'
export interface Tile{id:string;label:string;thumbnail_url?:string|null;original_url?:string|null;thumbnail_status?:string;original_media_type?:string|null;score?:number|null;media_kind?:"video"|"image"|null;play_url?:string|null;media_error?:string|null;duration?:number|null}
defineProps<{items:Tile[];canDelete?:boolean;showScores?:boolean}>()
const emit=defineEmits<{(e:'open',index:number):void;(e:'remove',id:string):void}>()
</script>
<template>
  <div class="photo-grid">
    <article v-for="(item,index) in items" :key="item.id" class="photo-item">
      <DeferredImage v-if="item.thumbnail_url&&(!item.thumbnail_status||item.thumbnail_status==='ready')"
        :key="item.thumbnail_url" :src="item.thumbnail_url" :alt="item.label" class="photo-thumb" lazy>
        <template #error><div class="photo-load-error">Не удалось загрузить превью</div></template>
      </DeferredImage>
      <div v-else class="photo-placeholder"
        :class="{'skeleton-shape':!item.original_media_type&&item.thumbnail_status!=='failed'}">
        <span v-if="item.media_error">Ошибка подготовки</span>
        <span v-else-if="item.original_media_type&&!item.media_kind">{{item.original_media_type.startsWith('video/')?'Видео':'Оригинал без превью'}}</span>
        <span v-else-if="item.thumbnail_status==='failed'">⚠ Ошибка превью</span>
        <span v-else class="visually-hidden">Подготовка превью</span>
      </div>
      <span v-if="item.media_kind==='video'" class="video-badge">▶ Видео<span v-if="item.duration"> · {{Math.round(item.duration)}} с</span></span>
      <div class="photo-caption"><span :title="item.label">{{item.label}}</span><span v-if="showScores&&item.score!=null">{{item.score.toFixed(3)}}</span></div>
      <button class="photo-select" type="button" :aria-label="'Открыть '+item.label" @click="emit('open',index)">Открыть</button>
      <button v-if="canDelete" class="btn small photo-menu" :aria-label="'Удалить '+item.label" @click="emit('remove',item.id)">×</button>
    </article>
  </div>
</template>

<style scoped>
.video-badge{position:absolute;inset:10px auto auto 10px;padding:3px 7px;border-radius:5px;background:#141414de;color:#fff;font-size:.75rem;pointer-events:none}
</style>
