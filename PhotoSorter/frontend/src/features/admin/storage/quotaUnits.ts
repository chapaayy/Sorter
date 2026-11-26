const GIB=1024**3
export const gibValue=(n?:number|null)=>n==null?'':String(n/GIB)
export function parseGib(value:string|number):number|null {
  if(String(value).trim()==='')return null
  const n=Number(value),bytes=Math.round(n*GIB)
  if(!Number.isFinite(n)||n<0||!Number.isSafeInteger(bytes))throw new Error('Введите допустимый неотрицательный размер в ГиБ')
  return bytes
}
