<script setup lang="ts">
import {ref} from 'vue'
import PageHeader from '../../components/ui/PageHeader.vue'
import Accounts from './users/Accounts.vue'
import AccessRequests from './users/AccessRequests.vue'

const accountRefresh=ref(0),requestRefresh=ref(0)
</script>

<template>
  <PageHeader eyebrow="УПРАВЛЕНИЕ ДОСТУПОМ" title="Администрирование"/>
  <section aria-label="Пользователи" class="stack">
    <Accounts :refresh-key="accountRefresh" @created="requestRefresh++"/>
    <AccessRequests :refresh-key="requestRefresh" @approved="accountRefresh++"/>
  </section>
</template>
