import {describe,it,expect} from 'vitest'
import {parseGib} from '../src/features/admin/storage/quotaUnits'
describe('numeric HTML quota fields',()=>{
  it('accepts the number emitted by Vue and the equivalent string',()=>{
    for(const value of [20,'20'])expect(parseGib(value)).toBe(21474836480)
    for(const value of [0.5,'0.5'])expect(parseGib(value)).toBe(536870912)
    for(const value of [0,'0'])expect(parseGib(value)).toBe(0)
    expect(parseGib('')).toBeNull()
    expect(parseGib('  ')).toBeNull()
  })
  it('rejects invalid and unsafe values',()=>{
    for(const value of [-1,NaN,Infinity,'20oops','0x20','Infinity',Number.MAX_SAFE_INTEGER])
      expect(()=>parseGib(value)).toThrow('Введите допустимый')
  })
})
