<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref,useId,watch} from 'vue'

export interface SelectOption {value:string;label:string;disabled?:boolean}
const props=withDefaults(defineProps<{
  modelValue:string
  options:SelectOption[]
  label:string
  placeholder?:string
  disabled?:boolean
}>(),{placeholder:'Выберите значение',disabled:false})
const emit=defineEmits<{(event:'update:modelValue',value:string):void}>()
const root=ref<HTMLElement|null>(null)
const trigger=ref<HTMLButtonElement|null>(null)
const open=ref(false)
const active=ref(-1)
const listId='select-'+useId()
const selected=computed(()=>props.options.find(item=>item.value===props.modelValue))
const display=computed(()=>selected.value?.label||props.placeholder)
const enabled=computed(()=>props.options.map((item,index)=>item.disabled?-1:index).filter(index=>index>=0))

function dismiss(){open.value=false;active.value=-1}
function show(){
  if(props.disabled||!enabled.value.length)return
  open.value=true
  const index=props.options.findIndex(item=>item.value===props.modelValue&&!item.disabled)
  active.value=index>=0?index:enabled.value[0]
}
function toggle(){open.value?dismiss():show()}
function pick(index:number){
  const item=props.options[index]
  if(!item||item.disabled)return
  emit('update:modelValue',item.value)
  dismiss()
  trigger.value?.focus()
}
function onKeydown(event:KeyboardEvent){
  if(props.disabled)return
  if(event.key==='Escape'){if(open.value){event.preventDefault();dismiss()}return}
  if(event.key==='Tab'){dismiss();return}
  if(event.key==='Enter'||event.key===' '){
    event.preventDefault()
    if(open.value)pick(active.value)
    else show()
    return
  }
  if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return
  event.preventDefault()
  if(!open.value){show();return}
  const allowed=enabled.value
  if(!allowed.length)return
  if(event.key==='Home')active.value=allowed[0]
  else if(event.key==='End')active.value=allowed[allowed.length-1]
  else {
    const position=allowed.indexOf(active.value)
    const offset=event.key==='ArrowDown'?1:-1
    active.value=allowed[(position+offset+allowed.length)%allowed.length]
  }
}
function onOutside(event:PointerEvent){
  if(root.value&&event.target instanceof Node&&!root.value.contains(event.target))dismiss()
}
watch(()=>props.disabled,disabled=>{if(disabled)dismiss()})
onMounted(()=>document.addEventListener('pointerdown',onOutside))
onBeforeUnmount(()=>document.removeEventListener('pointerdown',onOutside))
</script>

<template>
  <div ref="root" class="ui-select">
    <button
      ref="trigger"
      type="button"
      class="ui-select-trigger"
      role="combobox"
      aria-haspopup="listbox"
      :aria-label="label"
      :aria-expanded="open"
      :aria-controls="open?listId:undefined"
      :aria-activedescendant="open&&active>=0?listId+'-option-'+active:undefined"
      :disabled="disabled"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span class="ui-select-value" :class="{'ui-select-placeholder':!selected}">{{display}}</span>
    </button>
    <div v-if="open" :id="listId" role="listbox" :aria-label="label" class="ui-select-list">
      <div
        v-for="(item,index) in options"
        :id="listId+'-option-'+index"
        :key="item.value"
        class="ui-select-option"
        :class="{active:index===active,selected:item.value===modelValue}"
        role="option"
        :aria-selected="item.value===modelValue"
        :aria-disabled="item.disabled||undefined"
        @mousedown.prevent
        @mouseenter="!item.disabled&&(active=index)"
        @click="pick(index)"
      >{{item.label}}</div>
    </div>
  </div>
</template>
