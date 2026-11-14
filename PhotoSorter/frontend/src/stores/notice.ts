import {defineStore} from 'pinia'
import {ref} from 'vue'
export interface Notice{id:number;text:string;kind:'info'|'error'|'ok';action?:{to:string;label:string}}
let serial=0
export const useNoticeStore=defineStore('notice',()=>{
  const notices=ref<Notice[]>([])
  function remove(id:number){notices.value=notices.value.filter(n=>n.id!==id)}
  function add(text:string,kind:Notice['kind']='info',action?:Notice['action']){
    const id=++serial
    notices.value.push({id,text,kind,action})
    setTimeout(()=>remove(id),action?15000:6500)
  }
  return {notices,add,remove}
})
