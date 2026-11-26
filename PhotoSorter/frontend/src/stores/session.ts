import {defineStore} from 'pinia'
import {computed,ref} from 'vue'
import {api,post,onUnauthorized,ApiError} from '../api/client'
import {router} from '../app/router'
import type {User} from '../types/api'
export const useSessionStore=defineStore('session',()=>{
  const user=ref<User|null>(null),checked=ref(false),checkFailed=ref(false)
  const isOwner=computed(()=>user.value?.username==='admin')
  function level(key:string){return isOwner.value?'all':user.value?.permissions?.[key]??(!user.value?.permissions&&key.startsWith('results.')?'granted':'none')}
  function can(key:string,ownerId?:string|number|null){if(!user.value)return false;const value=level(key);return value==='all'||value==='granted'||(value==='own'&&(ownerId==null||String(ownerId)===String(user.value.id)))}
  const canResults=computed(()=>can('results.view'))
  const accountSections=['accounts.view','accounts.requests','accounts.roles','accounts.storage','accounts.history']
  const systemSections=['system.status','system.models','system.processing_view','system.performance_view','system.update_status','system.retention_view']
  function canPath(path:string){
    if(isOwner.value)return true
    const first='/'+path.split('/')[1]
    if(first==='/profile')return true
    if(first==='/fo')return can('photos.view')
    if(first==='/results')return canResults.value
    if(first==='/references')return can('references.view')
    if(first==='/queue')return can('queue.view')
    if(first==='/logs')return can('logs.view')&&can('queue.view')
    if(first==='/admin')return [...accountSections,...systemSections,'storage.view','storage.limits','storage.maintenance'].some(k=>can(k))
    return false
  }
  const home=computed(()=>['/fo','/results','/references','/queue','/logs','/admin','/profile'].find(canPath)||'/profile')
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
  return {user,checked,checkFailed,isOwner,canResults,home,can,level,canPath,check,login,logout,refreshPermissions}
})
