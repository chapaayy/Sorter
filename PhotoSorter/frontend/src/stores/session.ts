import {defineStore} from 'pinia'
import {computed,ref} from 'vue'
import {api,post,onUnauthorized,ApiError} from '../api/client'
import {router} from '../app/router'
import type {User} from '../types/api'
export const useSessionStore=defineStore('session',()=>{
  const user=ref<User|null>(null),checked=ref(false),checkFailed=ref(false)
  const isOwner=computed(()=>user.value?.username==='admin')
  const canResults=computed(()=>isOwner.value||user.value?.permissions?.['results.view']!=='none')
  const home=computed(()=>isOwner.value?'/fo':canResults.value?'/results':'/profile')
  async function refreshPermissions(){
    const previous=user.value
    if(!previous||isOwner.value)return
    try{const next=await api<User>('/auth/me');if(user.value===previous)user.value=next}
    catch(e){if(user.value===previous&&e instanceof ApiError&&e.status===401){user.value=null;checked.value=true;if(!router.currentRoute.value.meta.public)void router.replace({name:'login',query:{next:router.currentRoute.value.fullPath}})}}
  }
  async function check(){
    checked.value=false;checkFailed.value=false
    try{user.value=await api<User>('/auth/me')}
    catch(e){
      if(e instanceof ApiError&&e.status===401)user.value=null
      else{checkFailed.value=true;return}
    }
    checked.value=true
  }
  async function login(username:string,password:string){user.value=await post<User>('/auth/login',{username,password});checked.value=true}
  async function logout(){
    try{await post('/auth/logout',{})}
    finally{user.value=null;await router.replace({name:'login'})}
  }
  onUnauthorized(()=>{user.value=null;checked.value=true;if(!router.currentRoute.value.meta.public)void router.replace({name:'login',query:{next:router.currentRoute.value.fullPath}})})
  return {user,checked,checkFailed,isOwner,canResults,home,check,login,logout,refreshPermissions}
})
