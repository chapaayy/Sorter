import {defineStore} from 'pinia'
import {ref} from 'vue'
import {api,post,onUnauthorized} from '../api/client'
import {router} from '../app/router'
import type {User} from '../types/api'
export const useSessionStore=defineStore('session',()=>{
  const user=ref<User|null>(null),checked=ref(false)
  async function check(){try{user.value=await api<User>('/auth/me')}catch{user.value=null}finally{checked.value=true}}
  async function login(username:string,password:string){user.value=await post<User>('/auth/login',{username,password});checked.value=true}
  async function logout(){
    try{await post('/auth/logout',{})}
    finally{user.value=null;await router.replace({name:'login'})}
  }
  onUnauthorized(()=>{user.value=null;checked.value=true;if(router.currentRoute.value.name!=='login')void router.replace({name:'login',query:{next:router.currentRoute.value.fullPath}})})
  return {user,checked,check,login,logout}
})
