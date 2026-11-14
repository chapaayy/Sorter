<script setup lang="ts">
import {ref} from 'vue'
import UiIcon from '../../components/ui/UiIcon.vue'
const props=withDefaults(defineProps<{
  label:string; type?:'text'|'email'|'password'; autocomplete?:string; min?:number; max?:number
}>(),{type:'text',max:256})
const value=defineModel<string>({required:true})
const visible=ref(false)
</script>

<template>
  <div class="auth-field" :class="{'has-toggle':type==='password'}">
    <label>
      <input v-model="value" :type="visible?'text':type" :autocomplete="props.autocomplete"
        :minlength="min" :maxlength="max" placeholder=" " required
        :inputmode="type==='email'?'email':undefined" autocapitalize="none" :spellcheck="false"/>
      <span>{{label}}</span>
    </label>
    <button v-if="type==='password'" type="button" class="auth-eye" @click="visible=!visible"
      :aria-label="(visible?'Скрыть ':'Показать ')+label.toLowerCase()">
      <UiIcon :name="visible?'eye-off':'eye'" :size="19"/>
    </button>
  </div>
</template>
