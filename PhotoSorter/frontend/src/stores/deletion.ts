import {defineStore} from 'pinia'
import {ref} from 'vue'
/** Shared optimistic state while server performs asynchronous batch removal. */
export const useDeletionStore=defineStore('batch-deletion',()=>{
 const ids=ref<string[]>([])
 function mark(id:string){if(!ids.value.includes(id))ids.value.push(id)}
 function clear(id:string){ids.value=ids.value.filter(value=>value!==id)}
 function reconcile(batches:readonly {batch_id:string;delete_state:string}[]){
  for(const batch of batches){
   if(batch.delete_state==='delete_failed'||batch.delete_state==='deleted')clear(batch.batch_id)
  }
 }
 function pending(id:string){return ids.value.includes(id)}
 return {mark,clear,pending,reconcile}
})
