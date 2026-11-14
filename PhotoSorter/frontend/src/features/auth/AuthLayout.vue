<script setup lang="ts">
import './auth.css'
defineProps<{title:string;subtitle?:string}>()
</script>
<template>
  <main class="auth-page">
    <section class="auth-content" aria-labelledby="auth-title">
      <h1 id="auth-title">{{title}}</h1>
      <p v-if="subtitle" class="auth-intro">{{subtitle}}</p>
      <slot/>
    </section>
  </main>
</template>
