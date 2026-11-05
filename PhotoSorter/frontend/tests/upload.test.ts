import {describe,it,expect} from 'vitest'
import {directoryEntries,ALLOWED} from '../src/utils/upload'
describe('folder input',()=>{
  it('accepts only supported image extensions',()=>{
    expect(ALLOWED.test('IMG_001.JPG')).toBe(true)
    expect(ALLOWED.test('file.jpeg')).toBe(true)
    expect(ALLOWED.test('image.png')).toBe(true)
    expect(ALLOWED.test('video.mp4')).toBe(false)
    expect(ALLOWED.test('archive.zip')).toBe(false)
  })
  it('rejects empty folder',()=>{
    expect(()=>directoryEntries({length:0} as FileList)).toThrow('не найдено')
  })
})
