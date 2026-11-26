<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {accountsApi} from '../../../api/accounts'
import {errorText} from '../../../utils/format'
const data=ref<{enabled:boolean;pending:number}|null>(null),error=ref(''),busy=ref(false)
onMounted(async()=>{try{data.value=await accountsApi.registration()}catch(e){error.value=errorText(e)}})
async function toggle(){if(!data.value)return;busy.value=true;try{data.value=await accountsApi.setRegistration(!data.value.enabled);error.value=''}catch(e){error.value=errorText(e)}finally{busy.value=false}}
</script>
<template><section class="panel stack"><h2>Регистрация</h2><p v-if="error" class="alert error" role="alert">{{error}}</p><template v-if="data"><p class="meta">Необработанных заявок: {{data.pending}}</p><label class="row wrap"><input type="checkbox" :checked="data.enabled" :disabled="busy" @change="toggle"/>Принимать новые заявки</label></template></section></template>
