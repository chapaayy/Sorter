<script setup lang="ts">
import {ref} from 'vue'
import {post} from '../../api/client'
import {errorText} from '../../utils/format'
import AuthField from './AuthField.vue'
import AuthLayout from './AuthLayout.vue'

const email=ref(''),password=ref(''),confirmation=ref(''),comment=ref('')
const busy=ref(false),sent=ref(false),error=ref('')
async function submit(){
  if(busy.value)return
  error.value=''
  if(password.value!==confirmation.value){error.value='Пароли не совпадают.';return}
  if(!comment.value.trim()){error.value='Расскажите, кто вы и зачем нужен доступ.';return}
  busy.value=true
  try{
    await post('/auth/register',{email:email.value,password:password.value,confirmation:confirmation.value,comment:comment.value})
    password.value='';confirmation.value='';comment.value='';sent.value=true
  }catch(e){error.value=errorText(e)}finally{busy.value=false}
}
</script>
<template>
  <AuthLayout v-if="sent" title="Заявка отправлена" subtitle="Администратор проверит заявку. После одобрения вы сможете войти с этой почтой и паролем.">
    <RouterLink class="auth-button primary" :to="{name:'login'}">Вернуться ко входу</RouterLink>
  </AuthLayout>
  <AuthLayout v-else title="Запросить доступ" subtitle="Создайте пароль и расскажите, к каким фотоотчётам вам нужен доступ.">
    <form class="auth-form" @submit.prevent="submit">
      <AuthField v-model="email" label="Электронная почта" type="email" autocomplete="username" :max="254"/>
      <AuthField v-model="password" label="Пароль" type="password" autocomplete="new-password" :min="12"/>
      <AuthField v-model="confirmation" label="Повторите пароль" type="password" autocomplete="new-password" :min="12"/>
      <label class="auth-comment">
        <span>О себе и нужном доступе</span>
        <textarea v-model="comment" required maxlength="1500" placeholder="Кто вы и какие фотоотчёты хотите смотреть?"/>
      </label>
      <p v-if="error" class="auth-feedback" role="alert">{{error}}</p>
      <button type="submit" class="auth-button primary" :disabled="busy" :aria-busy="busy||undefined" :aria-label="busy?'Отправляем…':undefined">
        <span v-if="busy" class="btn-spinner" aria-hidden="true"></span>
        <template v-else>Отправить на модерацию</template>
      </button>
    </form>
    <RouterLink class="auth-back" :to="{name:'login'}">Вернуться ко входу</RouterLink>
  </AuthLayout>
</template>
