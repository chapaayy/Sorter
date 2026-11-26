<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {api} from '../../api/client'
import type {StorageAccountDetail,User} from '../../types/api'
import {errorText} from '../../utils/format'
import PageHeader from '../../components/ui/PageHeader.vue'
import BudgetSummary from '../admin/storage/BudgetSummary.vue'
import CategoryTable from '../admin/storage/CategoryTable.vue'
const data=ref<Pick<StorageAccountDetail,'account'|'categories'|'sampled_at'>|null>(null),profile=ref<User|null>(null),error=ref('')
onMounted(async()=>{try{[profile.value,data.value]=await Promise.all([api<User>('/auth/profile'),api<Pick<StorageAccountDetail,'account'|'categories'|'sampled_at'>>('/auth/storage')])}catch(e){error.value=errorText(e)}})
</script>
<template><PageHeader title="Личный аккаунт" eyebrow="ЛИЧНЫЕ ПАРАМЕТРЫ"/>
<section class="panel stack"><p v-if="error" role="alert" class="alert error">{{error}}</p><template v-if="profile"><h2>{{profile.display_name||profile.username}}</h2><p class="meta">{{profile.username}}</p></template>
<template v-if="data"><BudgetSummary v-if="data.account.quota" :budget="data.account.quota" title="Личная квота"/><CategoryTable :categories="data.categories" :unavailable="!data.sampled_at"/></template></section></template>
