const GIB=1024**3
export const gibValue=(n?:number|null)=>n==null?'':String(n/GIB)
export function parseGib(value:string|number):number|null {
  const raw=String(value).trim()
  if(raw==='')return null
  if(!/^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw))throw new Error('Введите допустимый неотрицательный размер в ГиБ')
  const n=Number(raw),bytes=Math.round(n*GIB)
  if(!Number.isFinite(n)||n<0||!Number.isSafeInteger(bytes))throw new Error('Введите допустимый неотрицательный размер в ГиБ')
  return bytes
}
