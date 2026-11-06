import {defineStore} from 'pinia'
import {ref,watch} from 'vue'

const STORAGE_KEY='ps.sidebar.collapsed'

/** Desktop navigation preference; mobile keeps its independent drawer. */
export const useSidebarStore=defineStore('sidebar',()=>{
  let initial=false
  try{initial=localStorage.getItem(STORAGE_KEY)==='1'}catch{/* Storage may be disabled. */}
  const collapsed=ref(initial)
  watch(collapsed,value=>{
    try{localStorage.setItem(STORAGE_KEY,value?'1':'0')}catch{/* Keep working without storage. */}
  })
  const toggle=()=>{collapsed.value=!collapsed.value}
  return {collapsed,toggle}
})
