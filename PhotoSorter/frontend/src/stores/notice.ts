import {defineStore} from 'pinia'
import {ref} from 'vue'
export interface Notice{id:number;text:string;kind:'info'|'error'|'ok'}
let serial=0
export const useNoticeStore=defineStore('notice',()=>{
  const notices=ref<Notice[]>([])
  function remove(id:number){notices.value=notices.value.filter(n=>n.id!==id)}
  function add(text:string,kind:Notice['kind']='info'){
    const id=++serial
    notices.value.push({id,text,kind})
    setTimeout(()=>remove(id),6500)
  }
  return {notices,add,remove}
})
