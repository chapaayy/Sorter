<script setup lang="ts">
withDefaults(defineProps<{
  variant:'tasks'|'gallery'|'split'|'lines'
  label?:string
  count?:number
}>(),{label:'Загрузка…'})
</script>

<template>
  <div class="loading-skeleton" :data-skeleton="variant" role="status">
    <span class="visually-hidden">{{label}}</span>
    <div v-if="variant==='tasks'" class="stack" aria-hidden="true">
      <div v-for="n in (count??3)" :key="n" class="task-card skeleton-task">
        <div class="task-card-identity">
          <span class="task-card-number skeleton-shape"/>
          <span class="task-card-thumbnail skeleton-shape"/>
          <div class="task-card-heading"><span class="skeleton-shape skeleton-line"/><span class="skeleton-shape skeleton-line short"/></div>
        </div>
        <span class="task-card-status skeleton-shape"/>
        <div class="task-card-progress"><span class="skeleton-shape skeleton-line"/><span class="skeleton-shape skeleton-line short"/></div>
        <div class="task-card-time"><span class="skeleton-shape skeleton-line short"/></div>
        <span class="task-card-actions skeleton-shape"/>
      </div>
    </div>
    <div v-else-if="variant==='split'" class="split skeleton-split" aria-hidden="true">
      <div class="mobile-picker"><span class="skeleton-shape skeleton-search"/></div>
      <div class="panel split-aside">
        <span class="split-search skeleton-shape skeleton-search"/>
        <div class="split-list">
          <div v-for="n in 5" :key="n" class="split-item">
            <span class="skeleton-shape skeleton-line"/><span class="skeleton-shape skeleton-count"/>
          </div>
        </div>
      </div>
      <div class="panel split-main">
        <span class="skeleton-shape skeleton-line skeleton-gallery-heading"/>
        <div class="photo-grid">
          <div v-for="n in (count??6)" :key="n" class="photo-item">
            <span class="photo-placeholder skeleton-shape"/><div class="photo-caption"><span class="skeleton-shape skeleton-line short"/></div>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="variant==='gallery'" class="photo-grid" aria-hidden="true">
      <div v-for="n in (count??6)" :key="n" class="photo-item">
        <span class="photo-placeholder skeleton-shape"/><div class="photo-caption"><span class="skeleton-shape skeleton-line short"/></div>
      </div>
    </div>
    <div v-else class="skeleton-lines" aria-hidden="true">
      <span v-for="n in (count??4)" :key="n" class="skeleton-shape skeleton-line" :class="{short:n%2===0}"/>
    </div>
  </div>
</template>
