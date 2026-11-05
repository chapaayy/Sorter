import {describe,it,expect} from 'vitest'
import {bytes,date,duration,isActive,isComplete,friendlySam,nameFromPath} from '../src/utils/format'
describe('display formatters',()=>{
  it('formats bytes at correct boundaries',()=>{
    expect(bytes(0)).toBe('0 Б')
    expect(bytes(1024)).toContain('КБ')
    expect(bytes(1024**3)).toContain('ГБ')
    expect(bytes(null)).toBe('—')
  })
  it('never invents unknown duration or date',()=>{
    expect(duration(null)).toBe('—')
    expect(duration(NaN)).toBe('—')
    expect(date('garbage')).toBe('—')
  })
  it('distinguishes lifecycle statuses and unassigned SAM',()=>{
    expect(isActive('queued')).toBe(true)
    expect(isActive('interrupted')).toBe(false)
    expect(isComplete('completed_with_errors')).toBe(true)
    expect(isComplete('failed')).toBe(false)
    expect(friendlySam('_Неопределено')).toBe('Неопределено')
    expect(nameFromPath('/folder/photo.jpg')).toBe('photo.jpg')
  })
})
