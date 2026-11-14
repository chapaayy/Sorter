import {defineStore} from 'pinia'
import {ref} from 'vue'
/** Shared optimistic state while server performs asynchronous batch removal. */
export const useDeletionStore=defineStore('batch-deletion',()=>{
 const requests=ref<Record<string,string>>({})
 function mark(id:string,name:string){requests.value[id]=name}
 function clear(id:string){delete requests.value[id]}
 function reconcile(batches:readonly {batch_id:string;delete_state:string}[]){
  for(const batch of batches){
   if(batch.delete_state==='delete_failed'||batch.delete_state==='deleted')clear(batch.batch_id)
  }
 }
 function pending(id:string){return Object.hasOwn(requests.value,id)}
 return {requests,mark,clear,pending,reconcile}
})
