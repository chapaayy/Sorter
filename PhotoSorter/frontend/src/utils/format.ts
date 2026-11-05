export function bytes(size: number | null | undefined): string {
  if (size == null || !Number.isFinite(size) || size < 0) return '—'
  if (size === 0) return '0 Б'
  const units = ['Б','КБ','МБ','ГБ','ТБ']
  const i = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1)
  return new Intl.NumberFormat('ru-RU',{ maximumFractionDigits:i===0?0:1 }).format(size/1024**i)+' '+units[i]
}
export function date(value?: string | null): string {
  if (!value) return '—'
  const d=new Date(value)
  return Number.isFinite(d.getTime())?d.toLocaleString('ru-RU',{dateStyle:'short',timeStyle:'short'}):'—'
}
export function duration(value?: number | null): string {
  if (value==null || !Number.isFinite(value) || value<0) return '—'
  const s=Math.round(value),h=Math.floor(s/3600),m=Math.floor(s%3600/60)
  return [h?h+' ч':'',m?m+' мин':'',s%60+' с'].filter(Boolean).join(' ')
}
export const runLabels:Record<string,string>={queued:'В очереди',running:'Обработка',stopping:'Остановка',completed:'Завершено',completed_with_errors:'С ошибками',stopped:'Остановлено',failed:'Ошибка',interrupted:'Прервано'}
export const isActive=(s?:string)=>['queued','running','stopping'].includes(s||'')
export const isComplete=(s?:string)=>['completed','completed_with_errors'].includes(s||'')
export const nameFromPath=(p?:string)=>(p||'').split(/[\\/]/).pop()||'Фотография'
export const friendlySam=(s:string)=>s==='_Неопределено'?'Неопределено':s
export const errorText=(e:unknown)=>e instanceof Error?e.message:String(e)
