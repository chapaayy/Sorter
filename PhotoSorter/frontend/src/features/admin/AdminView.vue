<script setup lang="ts">
import PageHeader from '../../components/ui/PageHeader.vue'
import AccessRequests from './users/AccessRequests.vue'
</script>

<template>
  <PageHeader eyebrow="УПРАВЛЕНИЕ ДОСТУПОМ" title="Администрирование"/>
  <section aria-label="Пользователи"><AccessRequests/></section>
</template>
