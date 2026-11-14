<script setup lang="ts">
export interface Tile{id:string;label:string;thumbnail_url?:string|null;original_url?:string|null;thumbnail_status?:string;original_media_type?:string|null;score?:number|null}
defineProps<{items:Tile[];canDelete?:boolean;showScores?:boolean}>()
const emit=defineEmits<{(e:'open',index:number):void;(e:'remove',id:string):void}>()
</script>
<template>
  <div class="photo-grid">
    <article v-for="(item,index) in items" :key="item.id" class="photo-item">
      <img v-if="item.thumbnail_url&&(!item.thumbnail_status||item.thumbnail_status==='ready')" class="photo-thumb"
        :src="item.thumbnail_url" :alt="item.label" loading="lazy" decoding="async" @error="($event.target as HTMLImageElement).style.visibility='hidden'"/>
      <div v-else class="photo-placeholder">
        <span v-if="item.original_media_type">{{item.original_media_type.startsWith('video/')?'Видео':'Оригинал без превью'}}<br>Скачать оригинал</span>
        <span v-else>{{item.thumbnail_status==='failed'?'⚠ Ошибка превью':'◌ Подготовка превью'}}</span>
      </div>
      <div class="photo-caption"><span :title="item.label">{{item.label}}</span><span v-if="showScores&&item.score!=null">{{item.score.toFixed(3)}}</span></div>
      <a v-if="item.original_media_type&&item.original_url" class="photo-select" :href="item.original_url"
        :aria-label="'Скачать '+item.label" download>Скачать</a>
      <button v-else class="photo-select" type="button" :aria-label="'Открыть '+item.label" @click="emit('open',index)">Открыть</button>
      <button v-if="canDelete" class="btn small photo-menu" :aria-label="'Удалить '+item.label" @click="emit('remove',item.id)">×</button>
    </article>
  </div>
</template>
