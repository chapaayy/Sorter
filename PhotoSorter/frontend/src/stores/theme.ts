import {defineStore} from 'pinia'
import {ref,watch} from 'vue'
import type {ThemeChoice} from '../types/api'
export const useThemeStore=defineStore('theme',()=>{
  let initial='system'
  try{initial=localStorage.getItem('ps.theme')||'system'}catch{ /* private mode */ }
  const choice=ref<ThemeChoice>(['light','dark','system'].includes(initial)?initial as ThemeChoice:'system')
  const media=typeof matchMedia==='function'?matchMedia('(prefers-color-scheme: light)'):undefined
  const apply=()=>{document.documentElement.dataset.theme=choice.value==='system'?(media?.matches?'light':'dark'):choice.value}
  watch(choice,value=>{try{localStorage.setItem('ps.theme',value)}catch{}apply()},{immediate:true})
  media?.addEventListener('change',apply)
  return {choice}
})
