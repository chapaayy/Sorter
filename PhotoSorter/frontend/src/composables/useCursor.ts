import {ref,shallowRef} from 'vue'
import type {CursorPage} from '../types/api'
import {errorText} from '../utils/format'
export function useCursor<T>(fetcher:(cursor:string|null)=>Promise<CursorPage<T>>){
  const items=shallowRef<T[]>([]),cursor=ref<string|null>(null),loading=ref(false),error=ref('')
  let generation=0
  async function load(){
    if(loading.value)return
    const stamp=generation;loading.value=true;error.value=''
    try{
      const next=await fetcher(cursor.value)
      if(stamp!==generation)return
      items.value=items.value.concat(next.photos)
      cursor.value=next.next_cursor
    }catch(e){if(stamp===generation)error.value=errorText(e)}
    finally{loading.value=false}
  }
  async function reset(){
    generation++;items.value=[];cursor.value=null;loading.value=false
    await load()
  }
  return {items,cursor,loading,error,load,reset}
}
