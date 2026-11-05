<script setup lang="ts">
import {ref,onMounted,onUnmounted,computed} from 'vue'
const props=withDefaults(defineProps<{title:string;message:string;confirmLabel?:string;danger?:boolean;requiredText?:string;busy?:boolean}>(),{confirmLabel:'Подтвердить'})
const emit=defineEmits<{(e:'confirm'):void;(e:'cancel'):void}>()
const text=ref(''),input=ref<HTMLInputElement|null>(null)
const ready=computed(()=>!props.requiredText||text.value.trim()===props.requiredText.trim())
function key(event:KeyboardEvent){if(event.key==='Escape'&&!props.busy)emit('cancel')}
onMounted(()=>{document.addEventListener('keydown',key);input.value?.focus()})
onUnmounted(()=>document.removeEventListener('keydown',key))
</script>
<template>
  <Teleport to="body"><div class="modal-overlay" @click.self="!busy&&emit('cancel')">
    <section class="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-description">
      <h2 id="confirm-title">{{title}}</h2>
      <p id="confirm-description">{{message}}</p>
      <label v-if="requiredText" class="field"><span>Чтобы продолжить, введите <strong>{{requiredText}}</strong></span><input ref="input" v-model="text" autocomplete="off" /></label>
      <div class="modal-actions"><button class="btn" :disabled="busy" @click="emit('cancel')">Отмена</button>
        <button class="btn" :class="danger?'danger':'primary'" :disabled="busy||!ready" @click="emit('confirm')">{{busy?'Выполняется…':confirmLabel}}</button>
      </div>
    </section>
  </div></Teleport>
</template>
