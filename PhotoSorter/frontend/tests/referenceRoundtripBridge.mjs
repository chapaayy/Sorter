// Bridge used only by the compact PostgreSQL round-trip regression.
// Run production TS modules with Node's native type transformation; no npm install.
import {registerHooks} from 'node:module'
import {existsSync,readFileSync,writeFileSync} from 'node:fs'
import {fileURLToPath} from 'node:url'
import assert from 'node:assert/strict'

registerHooks({
  resolve(specifier,context,nextResolve){
    if(specifier.startsWith('.')&&context.parentURL?.startsWith('file:')){
      const url=new URL(specifier,context.parentURL)
      const ts=new URL(url.href+'.ts')
      if(existsSync(fileURLToPath(ts)))return nextResolve(ts.href,context)
    }
    return nextResolve(specifier,context)
  }
})
const {readReferenceZip}=await import('../src/utils/referenceZip.ts')
const {inspectPortableSelection}=await import('../src/utils/referencePortable.ts')
const {fileSha256,reviewReferences}=await import('../src/utils/referenceDuplicates.ts')
const [archive,output]=process.argv.slice(2)
assert.ok(archive&&output)
const signal=new AbortController().signal
const selection=await inspectPortableSelection(
  await readReferenceZip(new Blob([readFileSync(archive)]),signal),signal)
assert.deepEqual(selection.errors,[])
assert.ok(selection.catalog)
const checked=[]
for(const item of selection.tasks){
  const sha256=await fileSha256(item.entry.file)
  assert.ok(sha256)
  assert.equal(sha256,item.expectedSha256)
  checked.push({...item,sha256})
}
const review=reviewReferences(checked,checked.map(()=>false))
assert.equal(review.newFiles.length,checked.length)
assert.equal(review.duplicates.length,0)
const repeat=reviewReferences(checked,checked.map(()=>true))
assert.equal(repeat.newFiles.length,0)
assert.equal(repeat.duplicates.length,checked.length)
const photos=[]
for(const {sam,address,side,portable,sha256,entry} of review.newFiles){
  photos.push({sam,address:address??null,side:side??null,portable,sha256,
    relative_path:entry.relative,filename:entry.file.name,size:entry.file.size,
    bytes:Buffer.from(await entry.file.arrayBuffer()).toString('base64')})
}
writeFileSync(output,JSON.stringify({constructions:selection.catalog,photos}))
console.log('REFERENCE_PORTABLE_FRONTEND_ROUNDTRIP_OK')
