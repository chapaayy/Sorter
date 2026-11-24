import {test,expect,Page,Locator} from '@playwright/test'
import {mkdtemp,mkdir,rm,writeFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import {join} from 'node:path'
import type {Batch} from '../src/types/api'
const bid='a6d1a203-23d4-420b-a1c6-87c0f1100222'
const rid='20261105T100000-abcd1234abcd'
const pid='34b92d83-2461-4100-839f-28b7b63c9a27'
const batch={batch_id:bid,display_name:'Выезд Самара 05.11',created_at:'2026-11-05T06:00:00Z',upload_state:'sealed',thumbnail_state:'ready',delete_state:'active',photos:2,runs:1,size_bytes:2048000,pending:0}
const run={id:rid,batch_id:bid,status:'completed',models:{megaloc:{status:'completed',count:2,groups:1}},started_at:'2026-11-05T06:05:00Z',progress:{stage:'export',current:2,total:2},grouping_threshold:.5}
const photo={id:pid,name:'screen_001.jpg',bytes:1024,created_at:'2026-11-05T06:00:00Z',thumbnail_status:'pending',thumbnail_url:'/api/thumbnails/'+pid,original_url:'/api/photos/'+pid+'/original'}
const output={index:0,assigned_sam:'SAM-0001',group_id:'G0001',score:.921,thumbnail_url:'/api/thumbnails/'+pid,image_url:'/api/images/'+rid+'/megaloc/0?kind=query'}
function respond(route:any,data:unknown){return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})}
const stat=(allocated_bytes:number,logical_bytes=allocated_bytes,files=1,hardlink_paths=0)=>({allocated_bytes,logical_bytes,files,hardlink_paths})
function storageFixture(stale=false){
  return {disk:{device:1,total_bytes:10000000000,used_bytes:4000000000,available_bytes:6000000000,used_fraction:.4,reserved_bytes:600000000,allocatable_bytes:5400000000},
    filesystems:{'1':{total_bytes:10000000000,used_bytes:4000000000,available_bytes:6000000000,map_allocated_bytes:350000000,outside_map_or_unexplained_bytes:3650000000}},
    categories_bytes:{},registry:{sampled_at:'2026-11-25T00:00:00Z',reconciled_at:'2026-11-25T00:00:00Z',started_at:'2026-11-24T23:59:00Z',partial:stale,stale,reconciling:false,pending_changes:0,errors:0,
      allocated_bytes:250000000,logical_bytes:350000000,categories:{fo_original:stat(250000000),result_media:stat(0,100000000,1,1)},temporary:stat(0,0,0),temporary_peak_bytes:0,reserved_bytes:0,
      reference_history:{objects:0,object_bytes:0,embeddings:0,embedding_bytes:0,missing:0,partial:false},issues:{},missing_expected:0},
    host:{at:'2026-11-25T00:00:00Z',partial:false,stale:false,errors:0,categories:{postgres_data:stat(100000000)},devices:{'1':stat(100000000)},docker:{available:true,shared_engine_totals:[{Type:'Build Cache',Size:'1 GB',Reclaimable:'100 MB'}],map_revision_images:[],limitations:[]}}}
}
async function mock(page:Page){
  const defaults={auto_process_new_batches:false,grouping_threshold:.50,min_match_score:0,model:'megaloc'}
  const retention={enabled:true,value:2,unit:'months'}
  const workloads={mode:'manual',fo_threads:6,reference_threads:6,max_threads:7,
    total_cpus:8,model_cpus:6,system_cpus:2,max_model_cpus:7,
    background_policy:'cpu_shares_no_quota',model_limit_applies:'next_task',
    zip_mode:'on_demand',docker_limits_editable:false,applies:'next_task'}
  await page.route(/^https?:\/\/[^/]+\/api\//,async route=>{
    const url=new URL(route.request().url()),p=url.pathname,method=route.request().method()
    if(p==='/api/auth/me')return respond(route,{username:'admin'})
    if(p==='/api/auth/login')return respond(route,{username:'admin'})
    if(p==='/api/auth/logout')return respond(route,{ok:true})
    if(p==='/api/regions'){
      if(method==='POST')return respond(route,{code:route.request().postDataJSON().code})
      return respond(route,{regions:[
        {code:'SAM',constructions:12},{code:'MSK',constructions:5},{code:'TLT',constructions:6}
      ]})
    }
    if(p==='/api/admin/users')return respond(route,{items:[],has_more:false})
    if(p==='/api/admin/access-requests')return respond(route,{items:[],has_more:false})
    if(p==='/api/batches')return respond(route,{batches:[batch],total:1})
    if(p==='/api/batches/'+bid)return respond(route,batch)
    if(p==='/api/batches/'+bid+'/gallery')return respond(route,{photos:[photo],next_cursor:null})
    if(p==='/api/batches/'+bid+'/pending')return respond(route,{uploads:[],total:0})
    if(p==='/api/batches/'+bid+'/runs')return respond(route,{runs:[run],total:1})
    if(p==='/api/thumbnails/status/'+bid+'/counts')return respond(route,{total:2,ready:2,failed:0})
    if(p==='/api/batches/'+bid+'/retention')return respond(route,{batch_id:bid,delete_state:'active',warning:false,download_confirmed_at:null,delete_after_at:null})
    if(p==='/api/batches/'+bid+'/downloads/confirm'&&method==='POST')return respond(route,{batch_id:bid,download_confirmed_at:'2026-11-05T06:50:00Z',delete_after_at:'2027-01-05T06:50:00Z',confirmed_run_id:rid})
    if(p==='/api/reference-library/status')return respond(route,{
      unified_queue_enabled:false,staged_imports_enabled:false,baseline_state:'ready',
      current_version:1,current_version_id:1,published_at:'2026-11-05T06:00:00Z',
      published_references:1,notice:false,pending_changes:0,notice_version_id:null
    })
    if(p==='/api/reference-library/events')return respond(route,{events:[]})
    if(p==='/api/work-queue')return respond(route,{tasks:[],total:0})
    if(p==='/api/references')return respond(route,{sam:[{sam:'SAM-0001',photos:1}],total:1})
    if(p==='/api/references/cache/status')return respond(route,{total:1,cached:1,current_signature:null})
    if(p==='/api/references/SAM-0001/photos')return respond(route,{photos:[photo],next_cursor:null})
    if(p==='/api/runs'){
      const scope=url.searchParams.get('scope')
      if(scope==='active')return respond(route,{runs:[],total:0})
      return respond(route,{runs:[run],total:1})
    }
    if(p==='/api/runs/'+rid)return respond(route,run)
    if(p==='/api/system/retention'){
      if(method==='PATCH')Object.assign(retention,JSON.parse(route.request().postData()||'{}'))
      return respond(route,retention)
    }
    if(p==='/api/processing-settings/workloads'){
      if(method==='PATCH')Object.assign(workloads,JSON.parse(route.request().postData()||'{}'))
      return respond(route,workloads)
    }
    if(p==='/api/processing-settings/cpu'){
      const current={threads:7,max_threads:8,applies:'next_task',docker_quota_changes:false}
      if(method==='PATCH')current.threads=Number(JSON.parse(route.request().postData()||'{}').threads)
      return respond(route,current)
    }
    if(p==='/api/processing-settings'){
      if(method==='PATCH')Object.assign(defaults,JSON.parse(route.request().postData()||'{}'))
      return respond(route,defaults)
    }
    if(p==='/api/models')return respond(route,{models:[{id:'megaloc',title:'MegaLoc',available:true,downloadable:true}],device:'cpu'})
    if(p==='/api/results/'+rid)return respond(route,run)
    if(p==='/api/results/'+rid+'/sam')return respond(route,{'SAM-0001':1,'_Неопределено':1})
    if(p==='/api/results/'+rid+'/groups')return respond(route,{'G0001':2})
    if(p==='/api/results/'+rid+'/photos')return respond(route,{photos:[output],next_cursor:null})
    if(p==='/api/storage/host-audit')return respond(route,{available:false,detail:'Host scan not run'})
    if(p==='/api/storage/usage')return respond(route,storageFixture())
    if(p==='/api/storage/accounting/issues')return respond(route,{files:[],missing:[],offset:0,limit:50,snapshot:'2026-11-25T00:00:00Z'})
    if(p==='/api/storage/maintenance')return respond(route,[])
    if(p==='/api/system/status')return respond(route,{at:'2026-11-05T06:00:00Z',worker:{queue:{},expected_threads:7},thumbnails:{queued:0},disk:{total_bytes:10000000000,available_bytes:6000000000,reserved_bytes:600000000},api:{uptime_seconds:400,latency:{samples:6,p50_ms:13,p95_ms:30},rss_peak_kib:90000}})
    if(p==='/api/logs/usage')return respond(route,{bytes:2000,budget_bytes:524288000})
    if(p==='/api/logs/'+rid+'/page')return respond(route,{events:[{at:'2026-11-05T06:02:00Z',level:'INFO',model:'megaloc',source:'MegaLoc',message:'Обработка завершена'}],next_cursor:null})
    if(p.includes('/api/thumbnails/'))return route.fulfill({status:202,contentType:'application/json',body:'{"detail":"pending"}'})
    return route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({detail:'Unexpected test API: '+p})})
  })
}
async function uploadFo(form:Locator){
  // New uploads require a report date. The legacy transfer scenarios use
  // processing date; date-entry validation is tested independently.
  await form.getByRole('checkbox',{name:'Использовать дату обработки'}).check()
  await form.getByRole('button',{name:'Загрузить',exact:true}).click()
}
async function confirmRegionStart(page:Page){
  const dialog=page.getByRole('dialog',{name:'Выбор регионов для обработки'})
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button',{name:'SAM'}).click()
  await dialog.getByRole('button',{name:'Обработать',exact:true}).click()
}
async function openQueue(page:Page){
  const drawer=page.getByRole('button',{name:'Открыть меню'})
  if(await drawer.isVisible())await drawer.click()
  await page.getByRole('link',{name:'Очередь',exact:true}).click()
  await expect(page).toHaveURL(/\/queue$/)
}
function holdTransfer(){
  let release=()=>{}
  const waiting=new Promise<void>(resolve=>{release=resolve})
  return {waiting,release}
}
test.beforeEach(async({page})=>{await mock(page)})
test('six navigation sections and real data bindings',async({page})=>{
  await page.goto('/fo')
  await expect(page.getByRole('heading',{name:'Фотоотчёты'})).toBeVisible()
  await expect(page.getByRole('link',{name:'Фотографии',exact:true})).toBeVisible()
  await expect(page.getByText('Выезд Самара 05.11').first()).toBeVisible()
  for(const [path,heading] of [['/references','Образцы'],['/queue','Очередь'],['/results','Результаты'],['/logs','Логи'],['/settings','Настройки']] as const){
    await page.goto(path)
    await expect(page.getByRole('heading',{name:heading,exact:true})).toBeVisible()
  }
})
test('main sections share header sizing and use plain text when empty',async({page})=>{
  await page.route('**/api/batches?*',route=>respond(route,{batches:[],total:0}))
  await page.route('**/api/references',route=>respond(route,{sam:[],total:0}))
  await page.route('**/api/runs?*',route=>respond(route,{runs:[],total:0}))
  const screens=[
    ['/fo','Пока нет фотоотчётов'],
    ['/references','Пока нет образцов'],
    ['/queue','Нет активных заданий'],
    ['/results','Пока нет результатов'],
    ['/logs','Пока нет запусков'],
    ['/settings',null]
  ] as const
  const top=(selector:string)=>page.locator(selector).evaluate(node=>{
    const rect=node.getBoundingClientRect()
    return {x:rect.x,y:rect.y,height:rect.height}
  })
  await page.goto('/fo')
  const header=await Promise.all(['.page-head .eyebrow','.page-head h1'].map(top))
  const buttonHeight=(await top('.page-head button')).height
  for(const [path,title] of screens){
    await page.goto(path)
    const fields=await Promise.all(['.page-head .eyebrow','.page-head h1'].map(top))
    await expect(page.locator('.page-head p')).toHaveCount(0)
    for(const [index,field] of fields.entries()){
      expect(field.x).toBeCloseTo(header[index].x)
      expect(field.y).toBeCloseTo(header[index].y)
      expect(field.height).toBeCloseTo(header[index].height)
    }
    for(const button of await page.locator('.page-head button').all())
      expect((await button.boundingBox())?.height).toBeCloseTo(buttonHeight)
    if(title){
      const empty=page.locator('.page-empty')
      await expect(empty).toHaveText(title)
      await expect(empty).toHaveCSS('text-align','center')
      await expect(empty).toHaveCSS('background-color','rgba(0, 0, 0, 0)')
      await expect(empty.locator('*')).toHaveCount(0)
    }
    if(path==='/queue'){
      await page.getByRole('button',{name:'История · 0'}).click()
      await expect(page.locator('.page-empty')).toHaveText('История пока пуста')
      await expect(page.getByText('✓',{exact:true})).toHaveCount(0)
    }
  }
})
test('FO gallery is separate and shows real original viewer',async({page})=>{
  await page.goto('/fo/'+bid)
  await expect(page.getByRole('heading',{name:'Выезд Самара 05.11'})).toBeVisible()
  await expect(page.getByText('Подготовка миниатюр').first()).toBeVisible()
  await page.getByRole('button',{name:'Открыть screen_001.jpg'}).click()
  await expect(page.getByRole('dialog',{name:'Просмотр фотографии'})).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog',{name:'Просмотр фотографии'})).not.toBeVisible()
})
test('full ZIP is ready for direct download without extra confirmation',async({page,browserName})=>{
  const filename='Выезд Самара 05.11.zip'
  let downloadRequests=0
  await page.route('**/api/download/'+rid,route=>{
    downloadRequests++
    return route.fulfill({
    contentType:'application/zip',headers:{'Content-Disposition':"attachment; filename*=UTF-8''"+encodeURIComponent(filename)},
    body:'test archive'
    })
  })
  await page.goto('/results/'+rid)
  await expect(page.getByRole('heading',{name:'Выезд Самара 05.11'})).toBeVisible()
  await expect(page.locator('.results-zip-bar')).toContainText('Результаты готовы')
  await expect(page.locator('.results-zip-bar')).toContainText('Автоудаление не назначено')
  await expect(page.getByRole('button',{name:/Скачать всю сортировку ZIP/})).toBeVisible()
  await expect(page.getByRole('button',{name:'Я сохранил полный архив'})).toHaveCount(0)
  // Chromium raises Playwright's download event; WebKit may preview a
  // generated archive instead. All browsers must still request the actual ZIP.
  const download=browserName==='chromium'?page.waitForEvent('download'):null
  await page.getByRole('button',{name:/Скачать всю сортировку ZIP/}).click()
  await expect.poll(()=>downloadRequests).toBe(1)
  if(download)expect((await download).suggestedFilename()).toBe(filename)
})
test('auto-processing preference defaults off and saves on the server',async({page})=>{
  await page.goto('/admin')
  const enabled=page.getByRole('checkbox',{name:'Автоматически обрабатывать загруженные ФО'})
  await expect(enabled).not.toBeChecked()
  await enabled.check()
  await expect(enabled).toBeChecked()
  await page.reload()
  await expect(enabled).toBeChecked()
})
test('storage settings persist minute-level automatic deletion',async({page})=>{
  await page.goto('/admin')
  await page.getByRole('button',{name:'Обслуживание',exact:true}).click()
  const enabled=page.getByRole('checkbox',{name:'Удалять старые фотоотчёты автоматически'})
  await expect(enabled).toBeChecked()
  await page.getByRole('spinbutton',{name:'Удалять через'}).fill('5')
  await page.getByRole('combobox',{name:'Единицы срока хранения'}).click()
  await page.getByRole('option',{name:'Минут'}).click()
  await page.getByRole('region',{name:'Хранилище'}).getByRole('button',{name:'Сохранить'}).click()
  await page.reload()
  await page.getByRole('button',{name:'Обслуживание',exact:true}).click()
  await expect(page.getByRole('spinbutton',{name:'Удалять через'})).toHaveValue('5')
  await expect(page.getByRole('combobox',{name:'Единицы срока хранения'})).toContainText('Минут')
})
test('theme setting works in light and dark',async({page})=>{
  await page.goto('/settings')
  await page.locator('.theme-option').filter({hasText:'Светлая'}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','light')
  await page.locator('.theme-option').filter({hasText:'Тёмная'}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
  await expect(page.getByRole('radio',{name:'Тёмная'})).toBeChecked()
  await page.emulateMedia({colorScheme:'light'})
  await page.locator('.theme-option').filter({hasText:'Системная'}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','light')
  await page.emulateMedia({colorScheme:'dark'})
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
})
test('mobile drawer allows navigation',async({page,isMobile})=>{
  test.skip(!isMobile,'Mobile layout only')
  await page.goto('/fo')
  await page.getByRole('button',{name:'Открыть меню'}).click()
  await page.getByRole('link',{name:'Настройки'}).click()
  await expect(page.getByRole('heading',{name:'Настройки',exact:true})).toBeVisible()
})

test('processing overview lives in Administration, run details in Queue',async({page})=>{
  await page.goto('/admin')
  await expect(page.getByRole('heading',{name:'MegaLoc',exact:true})).toBeVisible()
  await expect(page.getByText('Модель установлена')).toBeVisible()
  await expect(page.getByRole('heading',{name:'Производительность',exact:true})).toBeVisible()
  await expect(page.getByRole('slider',{name:'CPU модели'})).toBeVisible()
  await expect(page.getByRole('slider',{name:'Резерв CPU системы'})).toBeVisible()
  await page.goto('/queue/runs/'+rid)
  await expect(page.getByRole('heading',{name:'Выезд Самара 05.11'})).toBeVisible()
  await expect(page.getByRole('link',{name:'История очереди'})).toBeVisible()
  await page.goto('/processing')
  await expect(page).toHaveURL(/\/fo$/)
})
test('FO file selection closes without creating an upload',async({page})=>{
  await page.goto('/fo')
  await page.getByRole('button',{name:'+ Загрузить папку'}).click()
  const dialog=page.getByRole('dialog',{name:'Загрузить фотографии'})
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button',{name:'Закрыть',exact:true}).click()
  await expect(dialog).toBeHidden()
  await expect(page.locator('.upload-floating')).toHaveCount(0)
  await page.getByRole('button',{name:'+ Загрузить папку'}).click()
  await expect(dialog).toBeVisible()
})

test('folder imports ignore old name-based recovery and show the name assigned by the server',async({page})=>{
  const root=await mkdtemp(join(tmpdir(),'map-import-name-'))
  const folder=join(root,'Самара')
  const original=Buffer.from('one photo')
  const gate=holdTransfer()
  const newId='a6d1a203-23d4-420b-a1c6-87c0f1100223'
  const requests:{display_name:string;creation_request_id:string}[]=[]
  let files:any[]=[],finished=false
  try{
    await mkdir(folder)
    await writeFile(join(folder,'one.jpg'),original)
    await page.addInitScript(({key,id})=>localStorage.setItem(key,id),{key:'ps.folder:Самара:1:'+original.length,id:bid})
    await page.route('**/api/batches/'+bid,route=>respond(route,{...batch,runs:0,upload_manifest_state:'complete'}))
    await page.route('**/api/batches/'+bid+'/upload-manifest',route=>respond(route,{
      state:'complete',pending:0,files:[{upload_id:pid,relative_path:'Самара/one.jpg',
        filename:'one.jpg',size:original.length,state:'finalized',received:original.length}]
    }))
    await page.route('**/api/batches',route=>{
      if(route.request().method()!=='POST')return route.fallback()
      requests.push(route.request().postDataJSON())
      if(requests.length===1)return route.fulfill({status:503,body:''})
      return respond(route,{batch_id:newId,display_name:'Выезд 2'})
    })
    await page.route('**/api/batches/'+newId+'/upload-manifest',route=>{
      if(route.request().method()==='PUT')files=route.request().postDataJSON().files
      return respond(route,{state:finished?'complete':files.length?'waiting':'legacy',files,pending:finished?0:1})
    })
    await page.route('**/api/uploads/**',async route=>{
      if(route.request().method()==='PATCH'){
        await gate.waiting
        return respond(route,{offset:original.length})
      }
      if(route.request().url().endsWith('/finish')){finished=true;return respond(route,{path:'saved'})}
      return respond(route,{offset:0,size:original.length,finalized:false})
    })
    await page.goto('/fo')
    await page.getByRole('button',{name:'+ Загрузить папку'}).click()
    const form=page.getByRole('dialog',{name:'Загрузить фотографии'})
    await form.locator('input[webkitdirectory]').setInputFiles(folder)
    const name=form.getByLabel('Название фотоотчёта')
    await expect(name).toHaveValue('Самара')
    await name.fill('  ')
    await expect(form.getByRole('button',{name:'Загрузить',exact:true})).toBeDisabled()
    await name.fill('Выезд')
    await uploadFo(form)
    await expect(page.locator('.upload-floating')).toContainText('ФО · Выезд 2')
    expect(requests).toHaveLength(2)
    expect(requests[1]).toEqual(requests[0])
    expect(requests[0]!.display_name).toBe('Выезд')
    expect(requests[0]!.creation_request_id).toMatch(/^[\da-f-]{36}$/)
    await expect.poll(()=>files.length).toBe(1)
    expect(files[0].relative_path).toBe('Самара/one.jpg')
    gate.release()
    await expect(page.locator('.toast').filter({hasText:'Все файлы партии сохранены'})
      .getByRole('link',{name:'Открыть'})).toHaveAttribute('href','/fo/'+newId)
  }finally{gate.release();await rm(root,{recursive:true,force:true})}
})

test('resuming from a report uses its existing manifest and sends only the missing file',async({page})=>{
  const root=await mkdtemp(join(tmpdir(),'map-resume-folder-'))
  const folder=join(root,'Камера')
  const source=Buffer.from('photo')
  const registered=[['saved-id','saved.jpg'],['missing-id','missing.jpg']].map(([upload_id,filename])=>({
    upload_id,filename,relative_path:'Камера/'+filename,size:source.length
  }))
  let done=false,creates=0
  const sent:string[]=[]
  try{
    await mkdir(folder)
    await Promise.all(registered.map(file=>writeFile(join(folder,file.filename!),source)))
    await page.route('**/api/batches',route=>{
      if(route.request().method()!=='POST')return route.fallback()
      creates++
      return route.fulfill({status:409,body:''})
    })
    await page.route('**/api/batches/'+bid,route=>respond(route,{...batch,runs:0,upload_manifest_state:done?'complete':'waiting'}))
    await page.route('**/api/batches/'+bid+'/upload-manifest',route=>respond(route,{
      state:done?'complete':'waiting',expected:2,finalized:done?2:1,missing:done?0:1,pending:done?0:1,
      files:registered.map((file,i)=>({...file,state:i===0||done?'finalized':'not_started',received:i===0||done?source.length:0}))
    }))
    await page.route('**/api/uploads/**',route=>{
      const path=new URL(route.request().url()).pathname
      if(route.request().method()==='PATCH'){
        sent.push(path)
        return respond(route,{offset:source.length})
      }
      if(path.endsWith('/finish')){done=true;return respond(route,{path:'saved'})}
      return respond(route,{offset:0,size:source.length,finalized:false})
    })
    await page.goto('/fo/'+bid)
    await page.getByRole('button',{name:'Продолжить загрузку папки'}).click()
    const form=page.getByRole('dialog',{name:'Продолжить загрузку ФО'})
    await form.locator('input[webkitdirectory]').setInputFiles(folder)
    await expect(form.getByLabel('Название фотоотчёта')).toHaveCount(0)
    await form.getByRole('button',{name:'Продолжить',exact:true}).click()
    await expect(page.getByText(/Все файлы партии сохранены/)).toBeVisible()
    expect(creates).toBe(0)
    expect(sent).toEqual(['/api/uploads/missing-id'])
  }finally{await rm(root,{recursive:true,force:true})}
})

test('mixed folder upload keeps sending bytes across pages and only opens its batch on click',async({page})=>{
  const folder=await mkdtemp(join(tmpdir(),'map-fo-'))
  const source=Buffer.from('test photo for FO upload')
  const names=['IMG_3908 — копия.JPG','clip.MOV']
  const gate=holdTransfer()
  let sending=false,done=0,files:any[]=[]
  try{
    await Promise.all(names.map(name=>writeFile(join(folder,name),source)))
    await page.route('**/api/batches',route=>route.request().method()==='POST'
      ?respond(route,{batch_id:bid,display_name:route.request().postDataJSON().display_name}):route.fallback())
    await page.route('**/api/batches/'+bid,route=>respond(route,{...batch,photos:0,pending:0,runs:0}))
    await page.route('**/api/batches/'+bid+'/upload-manifest',route=>{
      if(route.request().method()==='PUT')files=route.request().postDataJSON().files
      return respond(route,{state:done===names.length?'complete':files.length?'waiting':'legacy',pending:files.length-done,files})
    })
    await page.route('**/api/batches/'+bid+'/gallery?*',route=>respond(route,{photos:[
      {...photo,name:names[0]},
      {...photo,id:'video-id',name:names[1],thumbnail_url:null,original_media_type:'video/quicktime',
        original_url:'/api/photos/video-id/original'}
    ],next_cursor:null}))
    await page.route('**/api/uploads/**',async route=>{
      if(route.request().method()==='PATCH'){
        sending=true
        await gate.waiting
        return respond(route,{offset:source.length})
      }
      if(route.request().url().endsWith('/finish')){done++;return respond(route,{path:'saved'})}
      return respond(route,{offset:0,size:source.length,finalized:false})
    })
    await page.goto('/fo')
    await page.getByRole('button',{name:'+ Загрузить папку'}).click()
    const dialog=page.getByRole('dialog',{name:'Загрузить фотографии'})
    await dialog.locator('input[webkitdirectory]').setInputFiles(folder)
    await uploadFo(dialog)
    await expect.poll(()=>sending).toBe(true)
    await expect(dialog).toBeHidden()
    const drawer=page.getByRole('button',{name:'Открыть меню'})
    if(await drawer.isVisible())await drawer.click()
    await page.getByRole('link',{name:'Образцы',exact:true}).click()
    await page.getByRole('button',{name:'+ Создать конструкцию'}).click()
    const refs=page.getByRole('dialog',{name:'Создать конструкцию'})
    await refs.getByRole('tab',{name:'Импорт папки'}).click()
    await expect(refs.getByText('Выбрать папку библиотеки')).toBeVisible()
    await expect(dialog).toBeHidden()
    await refs.getByRole('button',{name:'Закрыть',exact:true}).click()
    await openQueue(page)
    const indicator=page.getByRole('button',{name:/ФО · .*%/})
    await expect(indicator).toBeVisible()
    await indicator.click()
    const transfers=page.getByRole('dialog',{name:'Очередь загрузок'})
    await expect(transfers.getByRole('button',{name:'Приостановить'})).toBeVisible()
    await transfers.getByRole('button',{name:'Закрыть',exact:true}).click()
    expect(done).toBe(0)
    expect(files.map(file=>file.filename).sort()).toEqual([...names].sort())
    gate.release()
    const toast=page.locator('.toast').filter({hasText:'Все файлы партии сохранены'})
    await expect(toast).toBeVisible()
    await expect(page).toHaveURL(/\/queue$/)
    await expect(indicator).toBeHidden()
    await toast.getByRole('link',{name:'Открыть'}).click()
    await expect(page).toHaveURL(new RegExp('/fo/'+bid+'$'))
    await expect(page.getByRole('link',{name:'Скачать clip.MOV'})).toHaveCount(0)
    await page.getByRole('button',{name:'Открыть clip.MOV'}).click()
    await expect(page.getByRole('dialog',{name:'Просмотр видео'})).toContainText('Браузер не смог воспроизвести этот формат.')
  }finally{gate.release();await rm(folder,{recursive:true,force:true})}
})

test('gallery opens image and video previews without downloading while conversion runs',async({page})=>{
  const clip='77b1146a-613d-41b9-b8d6-e08c5902b175'
  const original='/api/photos/'+clip+'/preview',prepared='/api/photos/'+clip+'/prepared'
  let converted=false,downloads=0
  page.on('download',()=>downloads++)
  await page.route('**/api/batches/'+bid,route=>respond(route,{
    ...batch,runs:0,media_image_format:'jpg',media_video_format:'mp4',
    media_preparation:{state:converted?'completed':'running',completed_count:converted?2:0,total_count:2,failed_count:0}
  }))
  await page.route('**/api/batches/'+bid+'/gallery?*',route=>respond(route,{photos:[
    {...photo,name:'still.HEIC',original_media_type:'image/heic',thumbnail_status:'ready'},
    {...photo,id:clip,name:'clip.MOV',original_media_type:'video/quicktime',media_kind:'video',
      thumbnail_status:'ready',thumbnail_url:'/api/thumbnails/'+clip,
      preview_url:original,play_url:converted?prepared:null}
  ],next_cursor:null}))
  await page.route('**/api/thumbnails/*',route=>route.fulfill({contentType:'image/svg+xml',
    body:'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'}))
  const hold=holdTransfer()
  await page.route('**/api/photos/'+clip+'/*',async route=>{
    await hold.waiting
    await route.abort().catch(()=>{})
  })
  try{
    await page.goto('/fo/'+bid)
    await page.getByRole('button',{name:'Открыть still.HEIC'}).click()
    const still=page.getByRole('dialog',{name:'Просмотр фотографии'})
    await expect(still.getByRole('img',{name:'still.HEIC'})).toBeVisible()
    await expect(still).toContainText('Полный просмотр будет доступен после перекодирования.')
    await still.getByRole('button',{name:'Закрыть просмотр'}).click()
    await page.getByRole('button',{name:'Открыть clip.MOV'}).click()
    const video=page.getByRole('dialog',{name:'Просмотр видео'})
    await expect(video.locator('video')).toHaveAttribute('src',original)
    await video.locator('video').dispatchEvent('error')
    await expect(video.getByRole('status')).toContainText('Полный просмотр будет доступен после перекодирования.')
    await expect(video).toContainText('Полный просмотр будет доступен после перекодирования.')
    converted=true
    await expect(video.locator('video')).toHaveAttribute('src',prepared)
    expect(downloads).toBe(0)
  }finally{hold.release()}
})

test('pausing and resuming counts each saved file only once',async({page})=>{
  const folder=await mkdtemp(join(tmpdir(),'map-pause-'))
  const source=Buffer.from('photo bytes')
  const firstGate=holdTransfer(),resumeGate=holdTransfer()
  let files:any[]=[]
  const finalized=new Set<string>()
  let secondAttempts=0,firstChecks=0
  try{
    for(const name of ['first.jpg','second.jpg'])await writeFile(join(folder,name),source)
    await page.route('**/api/batches',route=>route.request().method()==='POST'
      ?respond(route,{batch_id:bid,display_name:route.request().postDataJSON().display_name}):route.fallback())
    await page.route('**/api/batches?*',route=>respond(route,{batches:[
      {...batch,display_name:'Тест загрузки',runs:0,upload_manifest_state:finalized.size===2?'complete':'waiting'},
      {...batch,batch_id:'a6d1a203-23d4-420b-a1c6-87c0f1100223',display_name:'Тест загрузки',upload_manifest_state:'waiting'}
    ],total:2}))
    await page.route('**/api/batches/'+bid,route=>respond(route,{...batch,photos:0,pending:0,runs:0}))
    await page.route('**/api/batches/'+bid+'/upload-manifest',route=>{
      if(route.request().method()==='PUT')files=route.request().postDataJSON().files
      return respond(route,{state:finalized.size===2?'complete':files.length?'waiting':'legacy',
        pending:files.length-finalized.size,files:files.map(file=>({...file,
          state:finalized.has(file.upload_id)?'finalized':'not_started',received:finalized.has(file.upload_id)?source.length:0}))})
    })
    await page.route('**/api/uploads/**',async route=>{
      const method=route.request().method(),path=new URL(route.request().url()).pathname
      const id=path.split('/')[3]!
      const file=files.find(file=>file.upload_id===id)
      if(method==='GET'&&file?.filename==='first.jpg')firstChecks++
      if(method==='PATCH'){
        if(file?.filename==='second.jpg'){
          const attempt=++secondAttempts
          await (attempt===1?firstGate.waiting:resumeGate.waiting)
          if(attempt===1){await route.abort().catch(()=>{});return}
        }
        return respond(route,{offset:source.length})
      }
      if(path.endsWith('/finish')){finalized.add(id);return respond(route,{path:'saved'})}
      return respond(route,{offset:0,size:source.length,finalized:finalized.has(id)})
    })
    await page.goto('/fo')
    await page.getByRole('button',{name:'+ Загрузить папку'}).click()
    const dialog=page.getByRole('dialog',{name:'Загрузить фотографии'})
    await dialog.locator('input[webkitdirectory]').setInputFiles(folder)
    await uploadFo(dialog)
    await expect.poll(()=>secondAttempts).toBe(1)
    const cards=page.getByRole('article',{name:'Фотоотчёт Тест загрузки',exact:true})
    const card=cards.first()
    await expect(card.getByRole('progressbar',{name:'Прогресс загрузки Тест загрузки'})).toHaveAttribute('aria-valuenow','50')
    await expect(card.getByText('Загружается',{exact:true})).toBeVisible()
    await expect(card.getByText('1 из 2 файлов · Передача файлов')).toBeVisible()
    await expect(card.getByText('Не обрабатывалось')).toHaveCount(0)
    await expect(cards.nth(1).getByText('Загрузка не завершена')).toBeVisible()
    await expect(cards.nth(1).getByRole('progressbar')).toHaveCount(0)
    await card.getByRole('button',{name:'Ход загрузки'}).click()
    const transfers=page.getByRole('dialog',{name:'Очередь загрузок'})
    await expect(transfers.getByText('1 из 2 файлов')).toBeVisible()
    await transfers.getByRole('button',{name:'Приостановить'}).click()
    firstGate.release()
    await expect(transfers.getByRole('button',{name:'Продолжить',exact:true})).toBeVisible()
    await transfers.getByRole('button',{name:'Закрыть',exact:true}).click()
    await expect(card.getByText('Приостановлено',{exact:true})).toBeVisible()
    await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow','50')
    await card.getByRole('button',{name:'Ход загрузки'}).click()
    await transfers.getByRole('button',{name:'Продолжить',exact:true}).click()
    await expect.poll(()=>secondAttempts).toBe(2)
    await expect(transfers.getByText('1 из 2 файлов')).toBeVisible()
    expect(firstChecks).toBe(1)
    resumeGate.release()
    await expect(page.getByText(/Все файлы партии сохранены/)).toBeVisible()
    await transfers.getByRole('button',{name:'Закрыть',exact:true}).click()
    await expect(card.getByText('Не обработано',{exact:true})).toBeVisible()
    await expect(card.getByRole('button',{name:'Ход загрузки'})).toHaveCount(0)
    expect(finalized.size).toBe(2)
  }finally{firstGate.release();resumeGate.release();await rm(folder,{recursive:true,force:true})}
})

test('resuming an individual FO does not abort on internal navigation',async({page})=>{
  const source=Buffer.from('partially sent photograph')
  const pendingId='47370c5c-dbe0-413e-928f-d365f50e2201'
  const gate=holdTransfer()
  let sending=false,finished=false
  await page.route('**/api/batches/'+bid,route=>respond(route,{...batch,runs:0,pending:finished?0:1}))
  await page.route('**/api/batches/'+bid+'/pending',route=>respond(route,{uploads:finished?[]:[{
    id:pendingId,filename:'resume.jpg',size:source.length,received:3,has_part:true,can_finalize:false,
    prefix_bytes:0,prefix_sha256:null
  }]}))
  await page.route('**/api/uploads/'+pendingId,async route=>{
    if(route.request().method()==='PATCH'){
      expect(route.request().headers()['upload-offset']).toBe('3')
      sending=true
      await gate.waiting
      return respond(route,{offset:source.length})
    }
    return respond(route,{offset:3,size:source.length,finalized:false})
  })
  await page.route('**/api/uploads/'+pendingId+'/finish',route=>{
    finished=true;return respond(route,{path:'resume.jpg'})
  })
  try{
    await page.goto('/fo/'+bid)
    await page.locator('input[id="pending-source-'+pendingId+'"]').setInputFiles({
      name:'resume.jpg',mimeType:'image/jpeg',buffer:source
    })
    await expect.poll(()=>sending).toBe(true)
    await openQueue(page)
    await expect(page.getByRole('button',{name:/ФО · resume.jpg.*%/})).toBeVisible()
    gate.release()
    await expect(page.getByText('Загрузка фото завершена: resume.jpg',{exact:true})).toBeVisible()
    await expect(page).toHaveURL(/\/queue$/)
  }finally{gate.release()}
})
test('construction list remains one line with ellipsis and a separate count',async({page,isMobile})=>{
  test.skip(isMobile,'Desktop split list only')
  const longName='SAM 0001 — Московское шоссе, 19 километр, улица Очень Длинная, дом 28А корпус 7, северная сторона, напротив торгового центра, рядом с выездом на эстакаду'
  await page.route('**/api/references',route=>respond(route,{
    sam:[{sam:'SAM 0001',display_name:longName,photos:7},
         {sam:'SAM 0002',display_name:'SAM 0002 — Гагарина 64',photos:12}],
    total:2
  }))
  await page.goto('/references')
  const list=page.locator('.split-list')
  const first=list.locator('.split-item').first()
  await expect(first).toHaveAttribute('title',longName)
  await expect(first.locator('.split-item-count')).toHaveText('7')
  await expect(first.locator('.split-item-label')).toHaveCSS('white-space','nowrap')
  await expect(first.locator('.split-item-label')).toHaveCSS('text-overflow','ellipsis')
  await expect(first.locator('.split-item-label')).toHaveCSS('overflow','hidden')
  expect(await first.locator('.split-item-label').evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(true)
  const heights=await list.locator('.split-item').evaluateAll(els=>els.map(el=>el.getBoundingClientRect().height))
  expect(heights).toEqual([48,48])
})

test('desktop navigation collapses to icons and remembers preference',async({page,isMobile})=>{
  test.skip(isMobile,'Desktop navigation only')
  await page.goto('/references')
  const shell=page.locator('.app-shell')
  const widthBefore=await page.locator('.sidebar').evaluate(el=>el.getBoundingClientRect().width)
  await page.getByRole('button',{name:'Свернуть боковое меню'}).click()
  await expect(shell).toHaveClass(/is-sidebar-collapsed/)
  await expect(page.locator('.sidebar .nav-link').first()).toHaveAttribute('title','Фотографии')
  await expect(page.getByRole('link',{name:'Образцы'})).toBeVisible()
  const widthAfter=await page.locator('.sidebar').evaluate(el=>el.getBoundingClientRect().width)
  expect(widthAfter).toBeLessThan(widthBefore)
  expect(widthAfter).toBe(74)
  expect(await page.evaluate(()=>localStorage.getItem('ps.sidebar.collapsed'))).toBe('1')
  await page.reload()
  await expect(page.locator('.app-shell')).toHaveClass(/is-sidebar-collapsed/)
  await page.getByRole('button',{name:'Развернуть боковое меню'}).click()
  await expect(page.locator('.app-shell')).not.toHaveClass(/is-sidebar-collapsed/)
  expect(await page.evaluate(()=>localStorage.getItem('ps.sidebar.collapsed'))).toBe('0')
})

test('saved desktop collapse does not affect the mobile navigation drawer',async({page,isMobile})=>{
  test.skip(!isMobile,'Mobile layout only')
  await page.addInitScript(()=>localStorage.setItem('ps.sidebar.collapsed','1'))
  await page.goto('/fo')
  await page.getByRole('button',{name:'Открыть меню'}).click()
  await expect(page.getByRole('link',{name:'Настройки'})).toBeVisible()
  await expect(page.getByRole('button',{name:'Свернуть боковое меню'})).toBeHidden()
  await page.getByRole('link',{name:'Настройки'}).click()
  await expect(page.getByRole('heading',{name:'Настройки',exact:true})).toBeVisible()
})

test('desktop references use the maximum responsive width without a resize handle',async({page,isMobile})=>{
  test.skip(isMobile,'Mobile uses the standard picker')
  await page.setViewportSize({width:1600,height:900})
  await page.addInitScript(()=>localStorage.setItem('ps.group-picker.width','250'))
  const library=holdTransfer()
  await page.route('**/api/references',async route=>{
    await library.waiting
    return respond(route,{sam:[{sam:'SAM-0001',photos:1}],total:1})
  })
  try{
    await page.goto('/references',{waitUntil:'domcontentloaded'})
    await expect(page.locator('.skeleton-split .split-aside')).toHaveCSS('width','720px')
    library.release()
    const aside=page.locator('aside.split-aside')
    await expect(aside).toHaveCSS('width','720px')
    await expect(page.locator('.split-resize-handle')).toHaveCount(0)
    await page.setViewportSize({width:1050,height:900})
    const layout=await aside.evaluate(el=>({
      list:el.getBoundingClientRect().width,split:el.parentElement!.clientWidth
    }))
    expect(layout.list).toBeCloseTo(layout.split-380,0)
    expect(layout.list).toBeLessThan(720)
    await page.setViewportSize({width:1600,height:900})
    await expect(aside).toHaveCSS('width','720px')
  }finally{library.release()}
})

test('result galleries use a stable panel and group search on desktop',async({page,isMobile})=>{
  test.skip(isMobile,'Mobile uses the standard picker')
  await page.goto('/results/'+rid)
  const aside=page.locator('aside.split-aside')
  await expect(aside).toBeVisible()
  const before=await aside.evaluate(el=>el.getBoundingClientRect().width)
  await expect(page.getByRole('separator',{name:'Изменить ширину списка конструкций'})).toHaveCount(0)
  const filter=aside.getByRole('textbox',{name:'Поиск групп'})
  await filter.fill('Нет такой конструкции')
  await expect(aside.getByText('Ничего не найдено')).toBeVisible()
  expect(await aside.evaluate(el=>el.getBoundingClientRect().width)).toBeCloseTo(before)
})

test('incomplete photo batch remains blocked in FO, not via a second launch form',async({page})=>{
  await page.route(/^https?:\/\/[^/]+\/api\/batches(?:\?.*)?$/,route=>
    respond(route,{batches:[{...batch,display_name:'321',photos:1313,pending:2,
      runs:0,upload_manifest_state:'waiting',latest_run:null}],total:1}))
  await page.goto('/fo')
  const card=page.getByRole('article',{name:'Фотоотчёт 321'})
  await expect(card.locator('.task-card-status')).toHaveText('Загрузка не завершена')
  await expect(card.getByRole('button',{name:'Обработать'})).toHaveCount(0)
  await page.goto('/queue')
  await expect(page.getByText('Нет активных заданий')).toBeVisible()
})
test('opening a batch finalizes already transferred pending files without resending bytes',async({page})=>{
  // Recovery actions are valid only before the first MegaLoc run.
  await page.route('**/api/batches/'+bid,route=>respond(route,{...batch,runs:0,pending:2}))
  const ids=['47370c5c-dbe0-413e-928f-d365f50e2201','23663a5e-a1ef-46a7-8e65-db423bb7dd5c']
  let pending=ids.map((id,index)=>({id,filename:index?'IMG_2831.JPG':'IMG_2828.JPG',
    size:4320388,received:4320388,updated_at:'2026-11-05T19:12:50Z',
    has_part:true,can_finalize:true,prefix_bytes:65536,prefix_sha256:'a'.repeat(64)}))
  const finalized:string[]=[]
  await page.route(/^https?:\/\/[^/]+\/api\/batches\/[a-f0-9-]+\/pending$/,route=>
    respond(route,{uploads:pending,total:pending.length}))
  await page.route(/^https?:\/\/[^/]+\/api\/uploads\/[a-f0-9-]+\/finish$/,route=>{
    expect(route.request().method()).toBe('POST')
    const id=route.request().url().split('/').at(-2)!
    finalized.push(id)
    pending=pending.filter(entry=>entry.id!==id)
    return respond(route,{path:'/data/uploads/'+id+'.jpg'})
  })
  await page.goto('/fo/'+bid)
  await expect.poll(()=>finalized.length).toBe(2)
  expect(finalized.sort()).toEqual([...ids].sort())
  await expect(page.getByRole('region',{name:'Незавершённые загрузки'})).toBeHidden()
  // Existing, finalized gallery images remain accessible.
  await expect(page.getByRole('button',{name:'Открыть screen_001.jpg'})).toBeVisible()
})
test('explicit cancellation only removes one selected unfinished transfer',async({page})=>{
  await page.route('**/api/batches/'+bid,route=>respond(route,{...batch,runs:0,pending:1}))
  const id='47370c5c-dbe0-413e-928f-d365f50e2201'
  let pending=[{id,filename:'IMG_2828.JPG',size:4320388,received:100,
    updated_at:'2026-11-05T19:12:50Z',has_part:true,can_finalize:false,
    prefix_bytes:100,prefix_sha256:'a'.repeat(64)}]
  let deleteCount=0
  await page.route(/^https?:\/\/[^/]+\/api\/batches\/[a-f0-9-]+\/pending$/,route=>
    respond(route,{uploads:pending,total:pending.length}))
  await page.route(/^https?:\/\/[^/]+\/api\/uploads\/[a-f0-9-]+$/,route=>{
    if(route.request().method()!=='DELETE')return route.continue()
    deleteCount++
    pending=[]
    return respond(route,{cancelled:true})
  })
  await page.goto('/fo/'+bid)
  await expect(page.getByText('IMG_2828.JPG')).toBeVisible()
  await page.getByRole('button',{name:'Отменить',exact:true}).click()
  await expect(page.getByRole('alertdialog',{name:'Отменить незавершённую передачу?'})).toBeVisible()
  await page.getByRole('button',{name:'Отменить передачу',exact:true}).click()
  await expect.poll(()=>deleteCount).toBe(1)
  await expect(page.getByRole('region',{name:'Незавершённые загрузки'})).toBeHidden()
})


test('FO cards show live MegaLoc progress and a confirmed stop action',async({page})=>{
  const active={...run,status:'running',progress:{
    stage_label:'Группировка ФО',current:17,total:40,
    stage_percent:42.5,overall_percent:23.1}}
  const visible={...batch,runs:1,latest_run:active,last_result_run_id:null}
  await page.route(/^https?:\/\/[^/]+\/api\/batches(?:\?.*)?$/,
    route=>respond(route,{batches:[visible],total:1}))
  let stopped=0
  await page.route('**/api/runs/'+rid+'/stop',route=>{
    stopped++
    active.status='stopping'
    return respond(route,{id:rid,status:'stopping'})
  })
  await page.goto('/fo')
  const card=page.getByRole('article',{name:'Фотоотчёт Выезд Самара 05.11'})
  await expect(card.getByText('Обработка', {exact:true})).toBeVisible()
  await expect(card.getByText('Группировка ФО',{exact:true})).toBeVisible()
  await expect(card.locator('.task-card-percent')).toHaveText('23%')
  await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow','23')
  await card.getByRole('button',{name:'Остановить обработку'}).click()
  await expect(page.getByRole('alertdialog',{name:'Остановить обработку MegaLoc?'})).toBeVisible()
  await page.getByRole('alertdialog').getByRole('button',{name:'Остановить'}).click()
  await expect.poll(()=>stopped).toBe(1)
  await expect(card.locator('.task-card-status')).toHaveText('Остановка')
})

test('FO progress animates between confirmed values and never advances on its own',async({page})=>{
  const start=new Date('2026-11-15T12:00:00Z')
  await page.emulateMedia({reducedMotion:'no-preference'})
  await page.clock.install({time:start})
  await page.clock.pauseAt(new Date(start.getTime()+500))
  const active={...run,status:'running',progress:{stage_label:'Группировка ФО',overall_percent:3}}
  const visible={...batch,latest_run:active}
  await page.route('**/api/batches?*',route=>respond(route,{batches:[visible],total:1}))
  await page.goto('/fo')
  const card=page.getByRole('article',{name:'Фотоотчёт Выезд Самара 05.11'})
  const label=card.locator('.task-card-percent')
  const bar=card.getByRole('progressbar')
  const readFill=()=>bar.locator('span').evaluate(el=>parseFloat(el.style.width))
  await expect(label).toHaveText('3%')

  active.progress.overall_percent=8
  await page.getByRole('button',{name:'Обновить',exact:true}).click()
  await expect(bar).toHaveAttribute('aria-valuenow','8')
  await expect(label).toHaveText('3%')
  await page.clock.runFor(400)
  await expect(label).toHaveText('5%')
  expect(await readFill()).toBeGreaterThan(5)
  expect(await readFill()).toBeLessThan(6)
  await page.clock.runFor(600)
  await expect(label).toHaveText('8%')
  await page.clock.runFor(5000)
  await expect(label).toHaveText('8%')
  expect(await readFill()).toBe(8)

  active.progress.overall_percent=34
  await page.getByRole('button',{name:'Обновить',exact:true}).click()
  await expect(bar).toHaveAttribute('aria-valuenow','34')
  await page.clock.runFor(300)
  active.status='completed'
  await page.getByRole('button',{name:'Обновить',exact:true}).click()
  await expect(label).toHaveText('100%')
  await page.clock.runFor(900)
  await expect(label).toHaveText('100%')
})

test('idle FIFO starts directly and uses the same card columns as a completed report',async({page,isMobile})=>{
  if(!isMobile)await page.setViewportSize({width:1440,height:900})
  const ready={...run,status:'queued',queue_position:1}
  const draft={...batch,batch_id:bid+'1',display_name:'Новый выезд',runs:0,latest_run:null as typeof ready|null}
  await page.route('**/api/batches?*',route=>respond(route,{batches:[
    {...batch,latest_run:run},draft
  ],total:2}))
  await page.route('**/api/runs',route=>{
    draft.latest_run=ready
    return respond(route,ready)
  })
  await page.goto('/fo')
  const card=page.getByRole('article',{name:'Фотоотчёт Новый выезд'})
  await card.getByRole('button',{name:'Обработать',exact:true}).click()
  await confirmRegionStart(page)
  await expect(card.locator('.task-card-status')).toHaveText('Запуск обработки')
  await expect(card.getByText('Ожидает своей очереди')).toHaveCount(0)
  if(!isMobile){
    const starts=await page.locator('.task-card-progress-track').evaluateAll(nodes=>
      nodes.map(node=>node.getBoundingClientRect().x))
    expect(starts).toHaveLength(2)
    expect(starts[0]).toBeCloseTo(starts[1]!,1)
  }
  ready.status='running'
  await expect(card.locator('.task-card-status')).toHaveText('Обработка',{timeout:2500})
})

test('FO progress updates immediately with reduced motion or a new run',async({page})=>{
  const start=new Date('2026-11-15T12:00:00Z')
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.clock.install({time:start})
  await page.clock.pauseAt(new Date(start.getTime()+500))
  const active={...run,status:'running',progress:{stage_label:'Группировка ФО',overall_percent:3}}
  const visible={...batch,latest_run:active}
  await page.route('**/api/batches?*',route=>respond(route,{batches:[visible],total:1}))
  await page.goto('/fo')
  const label=page.locator('.task-card-percent')
  await expect(label).toHaveText('3%')
  active.progress.overall_percent=8
  await page.getByRole('button',{name:'Обновить',exact:true}).click()
  await expect(label).toHaveText('8%')
  await page.emulateMedia({reducedMotion:'no-preference'})
  active.id='new-run'
  active.progress.overall_percent=10
  await page.getByRole('button',{name:'Обновить',exact:true}).click()
  await expect(label).toHaveText('10%')
})

test('FO card can start once and remove a queued run without deleting history',async({page})=>{
  const draft:Batch={...batch,photos:25,runs:0,latest_run:null,last_result_run_id:null}
  await page.route(/^https?:\/\/[^/]+\/api\/batches(?:\?.*)?$/,
    route=>respond(route,{batches:[draft],total:1}))
  let started=0,stopped=0
  await page.route('**/api/runs',route=>{
    if(route.request().method()==='POST'){
      started++
      draft.runs=1
      draft.latest_run={...run,status:'queued',queue_position:3}
      return respond(route,draft.latest_run)
    }
    return respond(route,{runs:[run],total:1})
  })
  await page.route('**/api/runs/'+rid+'/stop',route=>{
    stopped++
    draft.latest_run={...run,status:'stopped'}
    return respond(route,{status:'stopped'})
  })
  await page.goto('/fo')
  const card=page.getByRole('article',{name:'Фотоотчёт Выезд Самара 05.11'})
  await expect(card.locator('.task-card-status')).toHaveText('Не обработано')
  await card.getByRole('button',{name:'Обработать'}).click()
  await confirmRegionStart(page)
  await expect.poll(()=>started).toBe(1)
  await expect(card.getByText('№3 в очереди')).toBeVisible()
  await card.getByRole('button',{name:'Убрать из очереди'}).click()
  await page.getByRole('alertdialog').getByRole('button',{name:'Убрать из очереди'}).click()
  await expect.poll(()=>stopped).toBe(1)
  await expect(card.locator('.task-card-status')).toHaveText('Остановлено')
  await expect(card.getByRole('button',{name:'Повторить',exact:true})).toHaveCount(0)
  await card.getByLabel('Другие действия').click()
  await card.getByRole('button',{name:'Повторить обработку'}).click()
  await confirmRegionStart(page)
  await expect.poll(()=>started).toBe(2)
  await expect(card.getByText('№3 в очереди')).toBeVisible()
})

test('failed retry preserves prior successful results and paged batch history',async({page})=>{
  const last={...run,id:'20261106T000000-deadbeefeeee',status:'failed',error:'Synthetic error'}
  const detail={...batch,runs:2,latest_run:last,last_result_run_id:rid}
  await page.route('**/api/batches/'+bid,route=>respond(route,detail))
  await page.route(/^https?:\/\/[^/]+\/api\/batches\/[a-f0-9-]+\/runs(?:\?.*)?$/,route=>
    respond(route,{runs:[last,run],total:2}))
  await page.goto('/fo/'+bid)
  await expect(page.getByRole('region',{name:'Обработка MegaLoc для партии'})
    .getByTestId('fo-processing-status')).toHaveText('Ошибка')
  await expect(page.getByRole('link',{name:'Прошлые результаты'})).toHaveAttribute('href','/results/'+rid)
  await page.getByRole('button',{name:'История запусков (2)'}).click()
  const history=page.getByRole('region',{name:'История обработок партии'})
  await expect(history.getByText('Ошибка', {exact:true})).toBeVisible()
  await expect(history.getByRole('link',{name:'Результаты'})).toHaveAttribute('href','/results/'+rid)
})


test('unified queue shows all work, cancel action and a separate history view',async({page})=>{
  const first='20261106T000000-222222222222'
  const prep='92b3b221-9886-4cb0-9c7d-dc4ae9a2ed66'
  const task=(seq:number,kind:string,id:string,state:string)=>({
    seq,kind,state,created_at:'2026-11-06T20:00:00Z',
    started_at:state==='running'?'2026-11-06T20:01:00Z':null,
    finished_at:null,fo_run_id:kind==='fo_processing'?id:null,
    reference_job_id:kind==='reference_preparation'?id:null,
    session_id:null,total_count:kind==='reference_preparation'?3:null,
    completed_count:0,failed_count:0,error:null,stop_requested:false,
    batch_id:kind==='fo_processing'?bid:null,
    batch_name:kind==='fo_processing'?'Выезд Самара 05.11':null,fo_source:'manual'
  })
  let work=[task(1,'fo_processing',rid,'running'),
    task(2,'fo_processing',first,'queued'),
    task(3,'reference_preparation',prep,'queued')]
  let stops=0
  await page.route(/^https?:\/\/[^/]+\/api\/work-queue(?:\?.*)?$/,route=>{
    const scope=new URL(route.request().url()).searchParams.get('scope')
    return respond(route,{tasks:scope==='history'?[]:work,
      total:scope==='history'?0:work.length})
  })
  await page.route('**/api/runs/'+first+'/stop',route=>{
    stops++
    work=work.filter(item=>item.fo_run_id!==first)
    return respond(route,{id:first,status:'stopped'})
  })
  await page.goto('/queue')
  const queue=page.locator('.queue-task-row')
  await expect(queue).toHaveCount(3)
  await expect(queue.nth(0).locator('.task-card-number')).toHaveText('1')
  await expect(queue.nth(2).getByText('Подготовка образцов')).toBeVisible()
  await queue.nth(1).locator('.task-card-menu summary').click()
  await queue.nth(1).getByRole('button',{name:'Убрать из очереди'}).click()
  const confirm=page.getByRole('alertdialog',{name:'Остановить задачу?'})
  await confirm.getByRole('button',{name:'Остановить'}).click()
  await expect.poll(()=>stops).toBe(1)
  await expect(queue).toHaveCount(2)
  await page.getByRole('button',{name:/История/}).click()
  await expect(page.getByText('История пока пуста')).toBeVisible()
  await expect(page.getByText('Ожидают и выполняются')).toHaveCount(0)
})
test('System settings identify a lost Worker heartbeat',async({page})=>{
  await page.route('**/api/system/status',route=>respond(route,{
    at:'2026-11-06T22:00:00Z',worker:{queue:{queued:1},expected_threads:7},
    services:{megaloc:{alive:false,last_seen:'2026-11-06T21:00:00Z'}},
    thumbnails:{},disk:{total_bytes:100,available_bytes:90,reserved_bytes:1},
    api:{uptime_seconds:10,latency:{samples:0,p50_ms:null,p95_ms:null},rss_peak_kib:100}
  }))
  await page.goto('/admin')
  await expect(page.getByText('Нет свежего сигнала').first()).toBeVisible()
})
test('FO library notice appears once, shows events and requires explicit acknowledgement',async({page})=>{
  let unread=true,acks=0
  const v=13
  const status=()=>({
    unified_queue_enabled:true,staged_imports_enabled:true,
    baseline_state:'ready',current_version:v,current_version_id:v,
    published_at:'2026-11-07T09:00:00Z',published_references:545,
    last_fo_uploaded_at:'2026-11-06T09:00:00Z',
    acknowledged_version_id:unread?12:v,notice_version_id:unread?v:null,
    pending_changes:unread?1:0,notice:unread,
    message:'Образцы конструкций обновились с момента предыдущей загрузки ФО. Результаты новых обработок могут отличаться от прежних.'
  })
  await page.route('**/api/reference-library/status',route=>respond(route,status()))
  await page.route(/^https?:\/\/[^/]+\/api\/reference-library\/events(?:\?.*)?$/,route=>
    respond(route,{events:[{id:9,version_id:v,version_number:v,
      event_kind:'reference_prepared',actor:'system',
      created_at:'2026-11-07T09:00:00Z',details:{reference_count:545}}]}))
  await page.route('**/api/reference-library/notices/ack',route=>{
    expect(route.request().method()).toBe('POST')
    expect(JSON.parse(route.request().postData()||'{}').version_id).toBe(v)
    unread=false;acks++
    return respond(route,status())
  })
  await page.goto('/fo')
  expect(acks).toBe(0)
  await page.getByRole('button',{name:'+ Загрузить папку'}).click()
  const notice=page.locator('section[aria-label="Уведомление об обновлении образцов"]')
  await expect(notice).toBeVisible()
  await expect(notice.getByText('Результаты новых обработок могут отличаться от прежних.')).toBeVisible()
  await notice.getByRole('button',{name:'Что изменилось'}).click()
  await expect(notice.getByText('версия 13')).toBeVisible()
  expect(acks).toBe(0),'Viewing history must not acknowledge'
  await notice.getByRole('button',{name:'Понятно'}).click()
  await expect.poll(()=>acks).toBe(1)
  await expect(notice).toBeHidden()
  await page.reload()
  await page.getByRole('button',{name:'+ Загрузить папку'}).click()
  await expect(notice).toHaveCount(0)
  expect(acks).toBe(1)
})

for(const mode of ['single','folder'] as const)test('staged reference '+mode+' upload continues on another page',async({page})=>{
  const status={
    unified_queue_enabled:true,staged_imports_enabled:true,baseline_state:'ready',
    current_version:12,current_version_id:12,published_references:1,
    published_at:'2026-11-06T09:00:00Z',notice:false,pending_changes:0,
    notice_version_id:null
  }
  const source=Buffer.from('test reference image bytes for staged import')
  let registered:any=null,finished=false,queued=0,sending=false
  const gate=holdTransfer()
  const sam=mode==='single'?'SAM-0001':'SAM 0004'
  await page.route('**/api/references/import/preview',route=>respond(route,{
    errors:[],new_regions:[],entries:[{sam,folder:'SAM 0004 — Гагарина 64',existing:false}]
  }))
  await page.route('**/api/reference-library/status',route=>respond(route,status))
  await page.route(/^https?:\/\/[^/]+\/api\/runs(?:\?.*)?$/,route=>
    respond(route,{runs:[{...run,status:'running'}],total:1}))
  await page.route(/^https?:\/\/[^/]+\/api\/reference-imports(?:\/.*)?(?:\?.*)?$/,async route=>{
    const url=new URL(route.request().url())
    const path=url.pathname
    const method=route.request().method()
    if(path==='/api/reference-imports/compare')return respond(route,{duplicates:[false]})
    if(path==='/api/reference-imports'){
      if(method==='GET')return respond(route,{sessions:[],total:0})
      const payload=JSON.parse(route.request().postData()||'{}')
      return respond(route,{id:payload.client_session_id,state:'uploading',registered:false,
        expected:0,pending:0,files:[],preparation_state:'pending'})
    }
    if(method==='PUT'&&path.endsWith('/manifest')){
      registered=JSON.parse(route.request().postData()||'{}').files[0]
      return respond(route,{id:path.split('/')[3],state:'uploading',registered:true,
        expected:1,pending:1,files:[{...registered,state:'pending',received:0}],
        preparation_state:'pending'})
    }
    if(method==='GET'&&path.includes('/files/')){
      return respond(route,{upload_id:registered.upload_id,state:'pending',
        offset:0,size:source.length,sha256:registered.sha256})
    }
    if(method==='PATCH'&&path.includes('/files/')){
      // WebKit Playwright may omit Blob bytes from postDataBuffer() even when
      // the browser sends the request. Emulate the server-verified offset.
      expect(route.request().headers()['upload-offset']).toBe('0')
      expect(route.request().headers()['content-type']).toContain('application/octet-stream')
      sending=true
      await gate.waiting
      return respond(route,{offset:registered.size})
    }
    if(method==='POST'&&path.endsWith('/finish')){
      finished=true
      return respond(route,{sha256:registered.sha256,already_finalized:false})
    }
    if(method==='GET'){
      return respond(route,{id:path.split('/').at(-1),state:finished?'complete':'uploading',
        registered:true,expected:1,pending:finished?0:1,files:[],
        preparation_state:finished?'queued':'pending'})
    }
    if(method==='POST'&&path.endsWith('/complete')){
      queued++
      return respond(route,{state:'queued',queue_seq:2,
        preparation_job_id:'fafb3923-06cb-4478-b45b-e931a34582fa'})
    }
    return route.fulfill({status:404,contentType:'application/json',body:'{}'})
  })
  const folder=mode==='folder'?await mkdtemp(join(tmpdir(),'map-refs-')):null
  try{
    await page.goto('/references')
    if(folder){
      const construction=join(folder,'SAM 0004 — Гагарина 64')
      await mkdir(construction)
      await writeFile(join(construction,'new.jpg'),source)
      await page.getByRole('button',{name:'+ Создать конструкцию'}).click()
      await page.getByRole('dialog',{name:'Создать конструкцию'}).getByRole('tab',{name:'Импорт папки'}).click()
      await page.locator('.upload-drop input[webkitdirectory]').setInputFiles(folder)
      await page.getByRole('button',{name:'Загрузить и подготовить'}).click()
    }else{
      await page.getByRole('button',{name:'+ Добавить фото'}).click()
      await expect(page.getByRole('tab',{name:'Фото в конструкцию'})).toHaveAttribute('aria-selected','true')
      await page.locator('.upload-drop input[type="file"]').setInputFiles({
        name:'new.jpg',mimeType:'image/jpeg',buffer:source
      })
      await page.getByRole('button',{name:'Добавить фото',exact:true}).click()
    }
    await page.getByRole('button',{name:'ОК',exact:true}).click()
    await expect.poll(()=>sending).toBe(true)
    await openQueue(page)
    const indicator=page.getByRole('button',{name:/Образцы · .*%/})
    await expect(indicator).toBeVisible()
    await indicator.click()
    const transfers=page.getByRole('dialog',{name:'Очередь загрузок'})
    await expect(transfers.getByRole('button',{name:'Приостановить'})).toBeVisible()
    await transfers.getByRole('button',{name:'Закрыть',exact:true}).click()
    expect(finished).toBe(false)
    gate.release()
    await expect.poll(()=>queued).toBe(1)
    expect(finished).toBe(true)
    expect(registered.sam).toBe(sam)
    expect(registered.size).toBe(source.length)
    expect(registered.sha256).toMatch(/^[0-9a-f]{64}$/)
    await expect(page.getByText(mode==='folder'
      ?'Образцы загружены. Подготовка поставлена в общую очередь.'
      :'Файлы приняты. Подготовка образцов поставлена в очередь.')).toBeVisible()
    await expect(page).toHaveURL(/\/queue$/)
    await expect(indicator).toBeHidden()
  }finally{gate.release();if(folder)await rm(folder,{recursive:true,force:true})}
})

test('reference folder with only duplicates never starts transfer or creates a job',async({page})=>{
  let checked=0,writes=0
  await page.route('**/api/references/import/preview',route=>respond(route,{
    errors:[],new_regions:[],entries:[{sam:'SAM 0004',folder:'SAM 0004 — Гагарина 64',existing:true}]
  }))
  await page.route('**/api/reference-imports{,/**}',route=>{
    const path=new URL(route.request().url()).pathname
    if(path.endsWith('/compare')){
      const {files}=route.request().postDataJSON()
      expect(files).toEqual([{sam:'SAM 0004',sha256:expect.stringMatching(/^[0-9a-f]{64}$/),size:6}])
      checked++
      return respond(route,{duplicates:[true]})
    }
    writes++
    return route.fulfill({status:500,body:'Unexpected staging request'})
  })
  const folder=await mkdtemp(join(tmpdir(),'map-ref-duplicate-'))
  try{
    const construction=join(folder,'SAM 0004 — Гагарина 64')
    await mkdir(construction)
    await writeFile(join(construction,'copy.jpg'),'sample')
    await page.goto('/references')
    await page.getByRole('button',{name:'+ Создать конструкцию'}).click()
    const dialog=page.getByRole('dialog',{name:'Создать конструкцию'})
    await dialog.getByRole('tab',{name:'Импорт папки'}).click()
    await dialog.locator('input[webkitdirectory]').setInputFiles(folder)
    await dialog.getByRole('button',{name:'Загрузить и подготовить'}).click()
    await expect(dialog.getByText('Дубли — 1')).toBeVisible()
    await expect(dialog.getByText(/copy.jpg/)).toBeVisible()
    await expect(dialog.getByText('Новые фото — 0')).toBeVisible()
    await dialog.getByRole('button',{name:'ОК',exact:true}).click()
    await expect(dialog).toBeHidden()
    await expect(page.getByText('Все выбранные фото уже есть в библиотеке. В очередь ничего не добавлено.')).toBeVisible()
    await expect(page.getByText('К очереди',{exact:true})).toHaveCount(0)
    expect(checked).toBe(1)
    expect(writes).toBe(0)
  }finally{await rm(folder,{recursive:true,force:true})}
})

test('reference review cancels without changes and uploads only confirmed new photos',async({page})=>{
  const requests:string[]=[]
  const gate=holdTransfer()
  let registered:any
  await page.route('**/api/reference-imports{,/**}',async route=>{
    const path=new URL(route.request().url()).pathname
    if(path.endsWith('/compare')){
      const {files}=route.request().postDataJSON()
      expect(files[1].sha256).toBe(files[2].sha256)
      return respond(route,{duplicates:[true,false,false]})
    }
    const method=route.request().method()
    requests.push(method+':'+path)
    if(path==='/api/reference-imports')return respond(route,{})
    if(path.endsWith('/manifest')){
      const {files}=route.request().postDataJSON()
      expect(files).toHaveLength(1)
      registered=files[0]
      expect(registered.filename).toBe('new.jpg')
      return respond(route,{expected:1,files:[{...registered,state:'pending'}]})
    }
    if(method==='GET'&&path.includes('/files/'))return respond(route,{offset:0,state:'pending'})
    if(method==='PATCH'){
      await gate.waiting
      return respond(route,{offset:registered.size})
    }
    if(path.endsWith('/finish'))return respond(route,{sha256:registered.sha256})
    if(path.endsWith('/complete'))return respond(route,{state:'queued',queue_seq:2,preparation_job_id:'id'})
    return respond(route,{state:'complete',pending:0})
  })
  try{
    await page.goto('/references')
    await page.getByRole('button',{name:'+ Добавить фото'}).click()
    const dialog=page.getByRole('dialog',{name:'Добавить фото'})
    await dialog.locator('input[type="file"]').setInputFiles([
      {name:'stored.jpg',mimeType:'image/jpeg',buffer:Buffer.from('existing content')},
      {name:'new.jpg',mimeType:'image/jpeg',buffer:Buffer.from('new content')},
      {name:'second.jpg',mimeType:'image/jpeg',buffer:Buffer.from('new content')}
    ])
    await dialog.getByRole('button',{name:'Добавить фото',exact:true}).click()
    await expect(dialog.getByText('Дубли — 2')).toBeVisible()
    await expect(dialog.getByText('stored.jpg',{exact:true})).toBeVisible()
    await expect(dialog.getByText(/Повтор среди выбранных фото/)).toBeVisible()
    await expect(dialog.getByText('new.jpg',{exact:true})).toBeVisible()
    await dialog.getByRole('button',{name:'Отмена'}).click()
    await expect(dialog.getByText('Проверка на дубли завершена')).toBeHidden()
    expect(requests).toEqual([])
    await dialog.getByRole('button',{name:'Добавить фото',exact:true}).click()
    await dialog.getByRole('button',{name:'ОК',exact:true}).click()
    await expect.poll(()=>requests.filter(request=>request.startsWith('PATCH')).length).toBe(1)
    await page.locator('.upload-floating').click()
    await expect(page.getByRole('dialog',{name:'Очередь загрузок'}).getByText(/0 Б \/ 11 Б/)).toBeVisible()
    gate.release()
    await expect(dialog).toBeHidden()
    await expect(page.getByText('Файлы приняты. Подготовка образцов поставлена в очередь.')).toBeVisible()
    expect(requests.filter(request=>request.endsWith('/complete'))).toHaveLength(1)
  }finally{gate.release()}
})

test('desktop references scroll inside two panels without scrolling the whole page',async({page,isMobile})=>{
  test.skip(isMobile,'Touch layouts keep natural document scrolling')
  const references=Array.from({length:80},(_,i)=>{
    const sam='SAM '+String(i+1).padStart(4,'0')
    return {sam,photos:60,display_name:sam+' — Тестовая улица '+i}
  })
  const images=Array.from({length:60},(_,i)=>({
    id:'ref-'+i,name:'image_'+i+'.jpg',bytes:1024,
    created_at:'2026-11-07T12:00:00Z',thumbnail_status:'pending',
    thumbnail_url:'/api/thumbnails/ref-'+i,original_url:'/api/photos/ref-'+i+'/original'
  }))
  await page.route('**/api/references',route=>respond(route,{sam:references,total:4800}))
  await page.route(/\/api\/references\/SAM%200001\/photos/,route=>
    respond(route,{photos:images,next_cursor:null}))
  await page.goto('/references')
  const constructions=page.locator('.split-list')
  const gallery=page.locator('.reference-library-gallery-scroll')
  await expect(constructions.locator('.split-item')).toHaveCount(80)
  await expect(gallery.getByLabel('Галерея, 60 фотографий')).toHaveCount(1)
  const layout=await page.evaluate(()=>{
    const list=document.querySelector('.split-list') as HTMLElement
    const photos=document.querySelector('.reference-library-gallery-scroll') as HTMLElement
    return {
      windowHeight:innerHeight,documentHeight:document.documentElement.scrollHeight,
      listClient:list.clientHeight,listScroll:list.scrollHeight,
      photoClient:photos.clientHeight,photoScroll:photos.scrollHeight
    }
  })
  expect(layout.listClient).toBeGreaterThan(150)
  expect(layout.photoClient).toBeGreaterThan(150)
  expect(layout.documentHeight).toBeLessThanOrEqual(layout.windowHeight+2)
  expect(layout.listScroll).toBeGreaterThan(layout.listClient+150)
  expect(layout.photoScroll).toBeGreaterThan(layout.photoClient+150)
  await constructions.evaluate(el=>{el.scrollTop=140})
  await gallery.evaluate(el=>{el.scrollTop=180})
  expect(await constructions.evaluate(el=>el.scrollTop)).toBeGreaterThan(100)
  expect(await gallery.evaluate(el=>el.scrollTop)).toBeGreaterThan(100)
})

test('construction creation keeps standard, custom and folder import tabs in one dialog',async({page})=>{
  await page.goto('/references')
  await expect(page.getByRole('button',{name:'+ Загрузить образцы'})).toHaveCount(0)
  await page.locator('.page-head').getByRole('button',{name:'+ Создать конструкцию'}).click()
  const dialog=page.getByRole('dialog',{name:'Создать конструкцию'})
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('tab',{name:'Обычная'})).toHaveAttribute('aria-selected','true')
  const picker=dialog.getByRole('button',{name:/^SAM/})
  await expect(picker).toBeVisible()
  await picker.click()
  await dialog.getByRole('option',{name:/^MSK/}).click()
  await expect(dialog.getByRole('button',{name:/^MSK/})).toBeVisible()
  await dialog.getByRole('textbox',{name:'Номер конструкции'}).fill('0004')
  await dialog.getByRole('textbox',{name:'Адрес конструкции'}).fill('Гагарина 64')
  await expect(dialog.getByText('MSK 0004 — Гагарина 64')).toBeVisible()
  await dialog.getByRole('tab',{name:'Индивидуальная'}).click()
  await expect(dialog.getByRole('textbox',{name:'Индивидуальное название'})).toBeVisible()
  await dialog.getByRole('tab',{name:'Импорт папки'}).click()
  await expect(dialog.getByText('Выбрать папку библиотеки')).toBeVisible()
  await dialog.getByRole('tab',{name:'Обычная'}).click()
  await expect(dialog.getByText('MSK 0004 — Гагарина 64')).toBeVisible()
})

test('deletion shows server stages and progress instead of MegaLoc metrics',async({page})=>{
  let state='deleting'
  let progress={phase:'waiting_operations',done:0,total:null as number|null}
  await page.route(/^https?:\/\/[^/]+\/api\/batches(?:\?.*)?$/,route=>respond(route,{
    batches:state==='deleted'?[]:[{...batch,delete_state:state,deletion_progress:progress,latest_run:run,last_result_run_id:rid}],
    total:state==='deleted'?0:1
  }))
  await page.route('**/api/batches/'+bid+'/deletion',route=>respond(route,{
    batch_id:bid,delete_state:state,task:{progress}
  }))
  await page.goto('/fo')
  let card=page.getByRole('article',{name:'Фотоотчёт Выезд Самара 05.11'})
  await expect(card).toHaveClass(/task-card-deleting/)
  await expect(card.locator('.task-card-status')).toHaveText('Удаляется')
  await expect(card.locator('.task-card-actions')).toHaveCount(0)
  await expect(card.getByText('Ожидаем завершения скачивания или другой операции')).toBeVisible()
  await expect(card.getByRole('progressbar')).toBeVisible()
  await expect(card.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow',/./)
  await expect(card.locator('.task-card-time')).toHaveCount(0)
  progress={phase:'scanning',done:0,total:null}
  await expect(card.getByRole('progressbar')).toBeVisible()
  await expect(card.locator('.task-card-progress-moving')).toBeVisible()
  progress={phase:'files',done:25,total:50}
  await expect(card.getByRole('progressbar')).toHaveAttribute('aria-valuenow','50')
  await expect(card.getByText('50%',{exact:true})).toBeVisible()
  await expect(card.getByText('Удаляем оригиналы, результаты и временные файлы · 25 из 50 операций')).toBeVisible()
  await page.goto('/results')
  await expect(page.locator('.task-card').first()).toHaveClass(/task-card-deleting/)
  await expect(page.locator('.task-card-status').first()).toHaveText('Удаляется')
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow','50')
  state='delete_failed'
  await page.reload()
  card=page.locator('.task-card').first()
  await expect(card).toHaveClass(/task-card-danger/)
  await expect(card).not.toHaveClass(/task-card-deleting/)
  await expect(card.locator('.task-card-status')).toHaveText('Ошибка удаления')
  state='deleting'
  progress={phase:'database',done:49,total:50}
  await page.goto('/fo')
  await expect(page.getByText('Удаляем записи партии')).toBeVisible()
  state='deleted'
  await expect(page.getByText('Пока нет фотоотчётов')).toBeVisible()
  await expect(page.getByText('Партия «Выезд Самара 05.11» удалена')).toBeVisible()
})

test('a deletion faster than a status poll shows confirmation without invented progress',async({page})=>{
  let done=false
  await page.route('**/api/batches?*',route=>respond(route,{
    batches:done?[]:[{...batch,delete_state:'deleting',deletion_progress:{phase:'queued',done:0,total:null}}],total:done?0:1
  }))
  await page.route('**/api/batches/'+bid+'/deletion',route=>respond(route,{
    batch_id:bid,delete_state:done?'deleted':'deleting',task:{progress:
      done?{phase:'completed',done:47,total:47}:{phase:'queued',done:0,total:null}}
  }))
  await page.goto('/fo')
  const card=page.getByRole('article',{name:'Фотоотчёт Выезд Самара 05.11'})
  await expect(card.getByText('В очереди на удаление')).toBeVisible()
  await expect(card.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow',/./)
  done=true
  await expect(page.getByText('Партия «Выезд Самара 05.11» удалена')).toBeVisible()
  await expect(card).toHaveCount(0)
})

test('website transfer queue stays FIFO across two FO folders and references',async({page})=>{
  const root=await mkdtemp(join(tmpdir(),'map-transfer-queue-'))
  const firstGate=holdTransfer(),secondGate=holdTransfer(),refGate=holdTransfer()
  const secondId='a6d1a203-23d4-420b-a1c6-87c0f1100223'
  const created:string[]=[],started:string[]=[]
  const byId=new Map<string,{files:any[];done:Set<string>}>()
  const byUpload=new Map<string,string>()
  let registered:any,referenceFinished=false
  const selected=Buffer.from('new photo')
  try{
    for(const name of ['321','322','323']){
      const folder=join(root,name)
      await mkdir(folder)
      await writeFile(join(folder,'one.jpg'),selected)
      if(name==='321')await writeFile(join(folder,'two.jpg'),selected)
    }
    await page.route('**/api/batches',route=>{
      if(route.request().method()!=='POST')return route.fallback()
      const {display_name:name}=route.request().postDataJSON()
      created.push(name)
      const id=name==='321'?bid:secondId
      byId.set(id,{files:[],done:new Set()})
      return respond(route,{batch_id:id,display_name:name})
    })
    for(const id of [bid,secondId]){
      await page.route('**/api/batches/'+id,route=>respond(route,{...batch,batch_id:id,photos:0,pending:0,runs:0}))
      await page.route('**/api/batches/'+id+'/upload-manifest',route=>{
        const state=byId.get(id)!
        if(route.request().method()==='PUT'){
          state.files=route.request().postDataJSON().files
          for(const file of state.files)byUpload.set(file.upload_id,id)
          started.push(id===bid?'321':'322')
        }
        return respond(route,{state:state.files.length===0?'legacy':state.files.length===state.done.size?'complete':'waiting',
          pending:state.files.length-state.done.size,files:state.files})
      })
    }
    await page.route('**/api/uploads/**',async route=>{
      const path=new URL(route.request().url()).pathname
      const uploadId=path.split('/')[3]!,id=byUpload.get(uploadId)!
      const state=byId.get(id)!,file=state.files.find(f=>f.upload_id===uploadId)
      if(route.request().method()==='PATCH'){
        if(id===secondId)await secondGate.waiting
        else if(file.filename==='two.jpg')await firstGate.waiting
        return respond(route,{offset:selected.length})
      }
      if(path.endsWith('/finish')){
        state.done.add(uploadId)
        return respond(route,{path:'saved'})
      }
      return respond(route,{offset:0,size:selected.length,finalized:false})
    })
    await page.route('**/api/reference-imports{,/**}',async route=>{
      const path=new URL(route.request().url()).pathname
      if(path.endsWith('/compare'))return respond(route,{duplicates:[false]})
      if(path==='/api/reference-imports')return respond(route,{})
      if(path.endsWith('/manifest')){
        registered=route.request().postDataJSON().files[0]
        started.push('references')
        return respond(route,{expected:1,files:[{...registered,state:'pending'}]})
      }
      if(route.request().method()==='PATCH'){
        await refGate.waiting
        return respond(route,{offset:registered.size})
      }
      if(path.endsWith('/finish')){
        referenceFinished=true
        return respond(route,{sha256:registered.sha256})
      }
      if(path.endsWith('/complete'))return respond(route,{state:'queued',queue_seq:2,preparation_job_id:'id'})
      return respond(route,path.includes('/files/')?{state:'pending',offset:0}:
        {state:referenceFinished?'complete':'uploading',pending:referenceFinished?0:1})
    })
    await page.goto('/fo')
    async function addFo(name:string){
      await page.getByRole('button',{name:'+ Загрузить папку'}).click()
      const form=page.getByRole('dialog',{name:'Загрузить фотографии'})
      await form.locator('input[webkitdirectory]').setInputFiles(join(root,name))
      await uploadFo(form)
      await expect(form).toBeHidden()
    }
    const indicator=page.locator('.upload-floating')
    await addFo('321')
    await expect(indicator).toHaveText(/ФО · 321\s*50%/)
    await addFo('322')
    await addFo('323')
    const drawer=page.getByRole('button',{name:'Открыть меню'})
    if(await drawer.isVisible())await drawer.click()
    await page.getByRole('link',{name:'Образцы',exact:true}).click()
    await page.getByRole('button',{name:'+ Добавить фото'}).click()
    const form=page.getByRole('dialog',{name:'Добавить фото'})
    await form.locator('input[type="file"]').setInputFiles({name:'sample.jpg',mimeType:'image/jpeg',buffer:selected})
    await form.getByRole('button',{name:'Добавить фото',exact:true}).click()
    await form.getByRole('button',{name:'ОК',exact:true}).click()
    await expect(form).toBeHidden()
    await expect(indicator).toHaveText(/ФО · 321\s*50%/)
    await indicator.click()
    const transfers=page.getByRole('dialog',{name:'Очередь загрузок'})
    const rows=transfers.getByRole('listitem')
    await expect(rows).toHaveCount(4)
    await expect(rows.nth(1)).toContainText('322')
    await expect(rows.nth(1)).toContainText('Ждёт очереди')
    await expect(rows.nth(1).getByRole('progressbar')).toHaveCount(0)
    await expect(rows.nth(3)).toContainText('Образцы')
    await rows.nth(2).getByRole('button',{name:'Убрать из очереди'}).click()
    await expect(rows).toHaveCount(3)
    expect(started).toEqual(['321'])
    firstGate.release()
    await expect(rows.first()).toContainText('322')
    await expect.poll(()=>started).toEqual(['321','322'])
    await transfers.getByRole('button',{name:'Закрыть',exact:true}).click()
    await expect(indicator).toContainText('ФО · 322')
    secondGate.release()
    await expect(indicator).toContainText('Образцы · ')
    await expect.poll(()=>started).toEqual(['321','322','references'])
    refGate.release()
    await expect(indicator).toHaveCount(0)
    expect(created).toEqual(['321','322'])
  }finally{
    firstGate.release();secondGate.release();refGate.release()
    await rm(root,{recursive:true,force:true})
  }
})

test('settings are stacked and the theme cards preview the actual palettes',async({page})=>{
  await page.goto('/settings')
  const sections=page.locator('.settings-layout > section')
  await expect(sections).toHaveCount(3)
  await expect(sections.first().getByRole('heading',{name:'Оформление'})).toBeVisible()
  await expect(sections.nth(1).getByRole('heading',{name:'Загрузка файлов'})).toBeVisible()
  await expect(sections.last().getByRole('heading',{name:'О сервисе MAP'})).toBeVisible()
  const boxes=await sections.evaluateAll(nodes=>nodes.map(node=>{
    const bounds=node.getBoundingClientRect()
    return {left:bounds.left,top:bounds.top,bottom:bounds.bottom}
  }))
  for(let i=1;i<boxes.length;i++){
    expect(boxes[i]!.left).toBe(boxes[0]!.left)
    expect(boxes[i]!.top).toBeGreaterThan(boxes[i-1]!.bottom)
  }
  await expect(page.locator('.theme-preview-window')).toHaveCount(4)
  await expect(page.locator('.theme-preview-light .theme-preview-window')).toHaveCSS('background-color','rgb(250, 250, 250)')
  await expect(page.locator('.theme-preview-dark .theme-preview-window')).toHaveCSS('background-color','rgb(16, 16, 16)')
})

test('slow report data and slow thumbnails have distinct skeleton states',async({page})=>{
  const metadata=holdTransfer(),image=holdTransfer(),refresh=holdTransfer()
  let fetches=0
  const placeholder=page.locator('[data-skeleton="tasks"]')
  const thumbPath='/api/thumbnails/'+pid
  await page.emulateMedia({reducedMotion:'reduce'})
  await page.route('**/api/batches?*',async route=>{
    fetches++
    await (fetches===1?metadata:refresh).waiting
    return respond(route,{batches:[{...batch,cover_thumbnail_url:thumbPath}],total:1})
  })
  await page.route('**'+thumbPath,async route=>{
    await image.waiting
    return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10" fill="#777"/></svg>'})
  })
  try{
    await page.goto('/fo',{waitUntil:'domcontentloaded'})
    await expect(placeholder).toBeVisible()
    await expect(placeholder.locator('.skeleton-shape').first()).toHaveCSS('animation-name','none')
    await expect(page.getByText('Пока нет фотоотчётов')).toHaveCount(0)
    metadata.release()
    const card=page.getByRole('article',{name:'Фотоотчёт Выезд Самара 05.11'})
    await expect(card).toBeVisible()
    await expect(placeholder).toHaveCount(0)
    await expect(card.locator('.deferred-image-fill')).toBeVisible()
    image.release()
    await expect(card.locator('img')).toBeVisible()
    await expect(card.locator('.deferred-image-fill')).toHaveCount(0)
    await page.getByRole('button',{name:'Обновить',exact:true}).click()
    await expect.poll(()=>fetches).toBeGreaterThan(1)
    await expect(card).toBeVisible()
    await expect(placeholder).toHaveCount(0)
  }finally{metadata.release();image.release();refresh.release()}
})

test('reference gallery keeps the construction visible while photo tiles load',async({page})=>{
  const library=holdTransfer(),gallery=holdTransfer(),thumb=holdTransfer()
  await page.route('**/api/references',async route=>{
    await library.waiting
    return respond(route,{sam:[{sam:'SAM-0001',photos:1}],total:1})
  })
  await page.route('**/api/references/SAM-0001/photos?*',async route=>{
    await gallery.waiting
    return respond(route,{photos:[{...photo,thumbnail_status:'ready'}],next_cursor:null})
  })
  await page.route('**'+photo.thumbnail_url,async route=>{
    await thumb.waiting
    return route.fulfill({status:404,body:''})
  })
  try{
    await page.goto('/references',{waitUntil:'domcontentloaded'})
    await expect(page.locator('[data-skeleton="split"]')).toBeVisible()
    library.release()
    await expect(page.getByRole('heading',{name:'SAM-0001'})).toBeVisible()
    await expect(page.locator('[data-skeleton="gallery"]')).toBeVisible()
    gallery.release()
    await expect(page.getByText(photo.name,{exact:true})).toBeVisible()
    await expect(page.locator('[data-skeleton="gallery"]')).toHaveCount(0)
    await expect(page.locator('.photo-item .deferred-image-fill')).toBeVisible()
    thumb.release()
    await expect(page.getByText('Не удалось загрузить превью')).toBeVisible()
    await expect(page.locator('.photo-item .deferred-image-fill')).toHaveCount(0)
  }finally{library.release();gallery.release();thumb.release()}
})

test('administration lives outside Settings and is unavailable to viewers',async({page})=>{
  await page.goto('/settings')
  await expect(page.getByRole('heading',{name:'Настройки',exact:true})).toBeVisible()
  await expect(page.getByRole('region',{name:'Пользователи'})).toHaveCount(0)
  await expect(page.getByRole('heading',{name:'MegaLoc',exact:true})).toHaveCount(0)
  const drawer=page.getByRole('button',{name:'Открыть меню'})
  if(await drawer.isVisible())await drawer.click()
  await page.getByRole('link',{name:'Администрирование'}).click()
  await expect(page.getByRole('heading',{name:'Администрирование'})).toBeVisible()
  await expect(page.getByRole('region',{name:'Пользователи'})).toBeVisible()
  await expect(page.getByRole('region',{name:'Хранилище'})).toBeVisible()
  await expect(page.getByRole('heading',{name:'MegaLoc',exact:true})).toBeVisible()
  await page.route('**/api/auth/me',route=>respond(route,{username:'viewer@example.com'}))
  await page.goto('/admin')
  await expect(page).toHaveURL(/\/results$/)
  await expect(page.getByRole('link',{name:'Администрирование'})).toHaveCount(0)
})

test('mixed import defaults to JPG and MP4 and accepts an output profile',async({page})=>{
  await page.goto('/fo')
  await page.getByRole('button',{name:/Загрузить папку/}).click()
  const folder=await mkdtemp(join(tmpdir(),'sorter-media-import-'))
  try{
    await writeFile(join(folder,'picture.png'),Buffer.from('test PNG data'))
    await writeFile(join(folder,'clip.mov'),Buffer.from('test MOV data'))
    await page.locator('input[type=file][webkitdirectory]').setInputFiles(folder)
    const photos=page.getByLabel('Фото на выходе'),videos=page.getByLabel('Видео на выходе')
    await expect(photos).toHaveValue('jpg')
    await expect(videos).toHaveValue('mp4')
    await photos.selectOption('png')
    await videos.selectOption('webm')
    await page.route('**/api/batches',route=>respond(route,{batch_id:bid,display_name:'Смешанная папка'}))
    await page.route('**/api/batches/'+bid+'/upload-manifest',route=>respond(route,{state:'legacy',files:[]}))
    const submitted=page.waitForRequest(r=>r.method()==='PUT'&&r.url().includes('/upload-manifest'))
    await uploadFo(page.getByRole('dialog',{name:'Загрузить фотографии'}))
    const body=(await submitted).postDataJSON()
    expect(body.image_format).toBe('png')
    expect(body.video_format).toBe('webm')
    expect(body.files.map((f:{filename:string})=>f.filename).sort()).toEqual(['clip.mov','picture.png'])
  }finally{await rm(folder,{recursive:true,force:true})}
})

test('conversion is a distinct FIFO row and results open a video player',async({page})=>{
  await page.route('**/api/work-queue?**',route=>{
    const url=new URL(route.request().url())
    return respond(route,url.searchParams.get('scope')==='active'?{total:1,tasks:[{
      seq:27,kind:'media_preparation',media_batch_id:bid,fo_run_id:null,reference_job_id:null,
      batch_id:bid,batch_name:'Смешанная папка',state:'running',
      completed_count:1,total_count:4,failed_count:0,
      media_progress_percent:12,media_eta_seconds:36,media_current_file:'IMG_6113.MOV',
      started_at:'2026-11-05T06:05:00Z',created_at:'2026-11-05T06:00:00Z',
    }]}:{tasks:[],total:0})
  })
  await page.goto('/queue')
  await expect(page.getByText('Перекодирование файлов',{exact:true})).toBeVisible()
  await expect(page.getByText('Перекодирование файлов · 1 из 4 · IMG_6113.MOV')).toBeVisible()
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow','12')
  await expect(page.getByText('≈ 36 с')).toBeVisible()
  await page.route('**/api/results/'+rid+'/photos?**',route=>respond(route,{photos:[{
    ...output,filename:'Клип.mp4',media_kind:'video',duration:8,
    image_url:'/api/images/'+rid+'/megaloc/0?kind=copy',
  }],next_cursor:null}))
  await page.goto('/results/'+rid)
  await page.getByRole('button',{name:'Открыть Клип.mp4'}).click()
  const player=page.getByRole('dialog',{name:'Просмотр видео'}).locator('video')
  await expect(player).toHaveAttribute('src','/api/images/'+rid+'/megaloc/0?kind=copy')
  await expect(player).toHaveAttribute('controls','')
})

test('report detail shows confirmed video bytes instead of recovery alerts during transfer',async({page})=>{
  const folder=await mkdtemp(join(tmpdir(),'map-live-mov-'))
  const chunk=16*1024*1024, size=2*chunk, gate=holdTransfer()
  let secondChunk=false,done=false,pendingChecks=0,files:any[]=[]
  try{
    await writeFile(join(folder,'IMG_6113.MOV'),Buffer.alloc(size))
    await page.route('**/api/batches',route=>route.request().method()==='POST'
      ?respond(route,{batch_id:bid,display_name:'Видео'}):route.fallback())
    await page.route('**/api/batches/'+bid,route=>respond(route,{
      ...batch,display_name:'Видео',photos:0,videos:done?1:0,runs:0,pending:done?0:1,
      upload_manifest_state:done?'complete':'waiting',
    }))
    await page.route('**/api/batches/'+bid+'/pending',route=>{
      pendingChecks++
      return respond(route,{uploads:done?[]:[{id:pid,filename:'IMG_6113.MOV',size,received:0}],total:done?0:1})
    })
    await page.route('**/api/batches/'+bid+'/upload-manifest',route=>{
      if(route.request().method()==='PUT')files=route.request().postDataJSON().files
      return respond(route,{state:done?'complete':files.length?'waiting':'legacy',pending:done?0:files.length,files})
    })
    await page.route('**/api/uploads/**',async route=>{
      if(route.request().method()==='PATCH'){
        const offset=Number(route.request().headers()['upload-offset'])
        if(offset===chunk){secondChunk=true;await gate.waiting}
        return respond(route,{offset:offset+chunk})
      }
      if(route.request().url().endsWith('/finish')){done=true;return respond(route,{path:'saved'})}
      return respond(route,{offset:0,size,finalized:false})
    })
    await page.goto('/fo')
    await page.getByRole('button',{name:'+ Загрузить папку'}).click()
    const upload=page.getByRole('dialog',{name:'Загрузить фотографии'})
    await upload.locator('input[webkitdirectory]').setInputFiles(folder)
    await uploadFo(upload)
    await expect.poll(()=>secondChunk).toBe(true)
    // Navigate within the SPA, keeping the browser upload alive.
    const card=page.getByRole('article',{name:'Фотоотчёт Выезд Самара 05.11'})
    await card.getByLabel('Другие действия').click()
    await card.getByRole('link',{name:'Открыть фотографии'}).click()
    const panel=page.getByRole('region',{name:'Загрузка файлов',exact:true})
    await expect(panel.getByRole('progressbar')).toHaveAttribute('aria-valuenow','50')
    await expect(panel.getByText('IMG_6113.MOV')).toBeVisible()
    await expect(panel.getByText(/^16 МБ \/ 32 МБ$/)).toBeVisible()
    await expect(page.getByTestId('fo-processing-status')).toHaveText('Загружается')
    await expect(page.getByRole('region',{name:'Незавершённые загрузки'})).toHaveCount(0)
    expect(pendingChecks).toBe(0)
    gate.release()
    await expect(panel).toHaveCount(0)
    await expect(page.getByRole('button',{name:'Обработать',exact:true})).toBeVisible()
  }finally{gate.release();await rm(folder,{recursive:true,force:true})}
})

test('result gallery loads all 150 photos on scroll without hiding the last virtual row',async({page,isMobile})=>{
  const total=150
  const cursors:string[]=[]
  await page.route('**/api/results/'+rid+'/sam',route=>respond(route,{'SAM-0001':total}))
  await page.route('**/api/results/'+rid+'/photos?*',route=>{
    const url=new URL(route.request().url())
    const offset=Number(url.searchParams.get('cursor')||0)
    const end=Math.min(offset+60,total)
    cursors.push(String(offset))
    const photos=Array.from({length:end-offset},(_,i)=>{
      const index=offset+i
      return {index,filename:'IMG_'+String(index).padStart(4,'0')+'.JPG',
        assigned_sam:'SAM-0001',group_id:'G0001',score:0.713,media_kind:'image',
        thumbnail_url:null,image_url:'/api/images/'+rid+'/megaloc/'+index+'?kind=copy'}
    })
    return respond(route,{photos,next_cursor:end<total?String(end):null})
  })
  await page.goto('/results/'+rid)
  const grid=page.locator('.reference-library-gallery-scroll [aria-label^="Галерея,"]')
  await expect(grid).toHaveAttribute('aria-label','Галерея, 60 фотографий')
  async function scrollToEnd(){
    if(isMobile){
      await page.evaluate(()=>window.scrollTo(0,document.documentElement.scrollHeight))
    }else{
      await page.locator('.reference-library-gallery-scroll').evaluate(element=>{
        element.scrollTop=element.scrollHeight
      })
    }
  }
  await scrollToEnd()
  await expect(grid).toHaveAttribute('aria-label','Галерея, 120 фотографий')
  await scrollToEnd()
  await expect(grid).toHaveAttribute('aria-label','Галерея, 150 фотографий')
  await scrollToEnd()
  await expect(page.getByRole('button',{name:'Открыть IMG_0149.JPG'})).toBeVisible()
  expect(cursors).toEqual(['0','60','120'])
})

test('ZIP retention is compact and the extend action is preserved',async({page,isMobile})=>{
  const expires='2027-01-20T12:10:00Z'
  let extended=false
  await page.route('**/api/batches/'+bid+'/retention',route=>respond(route,{
    batch_id:bid,delete_state:'active',warning:false,delete_after_at:extended?'2027-03-20T12:10:00Z':expires
  }))
  await page.route('**/api/batches/'+bid+'/retention/extend',route=>{
    extended=true
    return respond(route,{batch_id:bid,delete_state:'active',warning:false,
      delete_after_at:'2027-03-20T12:10:00Z'})
  })
  await page.goto('/results/'+rid)
  const bar=page.locator('.results-zip-bar')
  await expect(bar).toContainText('Результаты готовы')
  await expect(bar).toContainText('Автоудаление:')
  await expect(bar.getByRole('button',{name:'Продлить хранение'})).toBeEnabled()
  const size=await bar.boundingBox()
  expect(size).not.toBeNull()
  if(!isMobile)expect(size!.height).toBeLessThan(72)
  await bar.getByRole('button',{name:'Продлить хранение'}).click()
  await expect(bar).toContainText('20.03.2027')
  expect(extended).toBe(true)
})

test('completed FO has Results as main action and retry only in Other actions',async({page})=>{
  const completed={...batch,runs:1,latest_run:run,last_result_run_id:rid}
  let started=0
  await page.route(/^https?:\/\/[^/]+\/api\/batches(?:\?.*)?$/,route=>
    respond(route,{batches:[completed],total:1}))
  await page.route('**/api/runs',route=>{
    if(route.request().method()==='POST'){
      started++
      completed.latest_run={...run,status:'queued',queue_position:2}
      completed.runs++
      return respond(route,completed.latest_run)
    }
    return respond(route,{runs:[run],total:1})
  })
  await page.goto('/fo')
  const card=page.getByRole('article',{name:'Фотоотчёт Выезд Самара 05.11'})
  await expect(card.getByRole('link',{name:'Результат',exact:true})).toHaveAttribute('href','/results/'+rid)
  await expect(card.locator('.task-card-actions > .task-card-action').getByText('Повторить')).toHaveCount(0)
  await card.getByLabel('Другие действия').click()
  await card.getByRole('button',{name:'Повторить обработку'}).click()
  await confirmRegionStart(page)
  await expect.poll(()=>started).toBe(1)
  await expect(card.getByRole('button',{name:'Убрать из очереди'})).toBeVisible()
})

test('read-only file inventory scans and displays per-file ownership',async({page})=>{
  await page.route('**/api/storage/inventory/scan',route=>respond(route,{
    snapshot_id:'test-snapshot',captured_at:'2026-11-23T12:00:00Z',
    files_scanned:2,allocated_bytes:4096,logical_bytes:8192,
    categories:{originals:{files:2,allocated_bytes:4096,logical_bytes:8192,hardlink_paths:1}},
    skipped_paths:0,partial:false,scan_seconds:0.02,checked_roots:['data','models'],
    not_scanned:['PostgreSQL files'],batch_metadata_available:true,
    description:'Snapshot'
  }))
  await page.route('**/api/storage/inventory/files?**',route=>respond(route,{
    snapshot_id:'test-snapshot',total:2,offset:0,limit:100,
    files:[
      {path:'PhotoSorter/data/uploads/batch/photo.jpg',category:'originals',
        purpose:'permanent',owner_kind:'batch',owner_id:'batch',
        owner_name:'Фотоотчёт 321',logical_bytes:4096,allocated_bytes:4096,
        hardlink:false,links:2,modified_at:'2026-11-23T12:00:00Z'},
      {path:'PhotoSorter/data/outputs/run/photo.jpg',category:'originals',
        purpose:'permanent',owner_kind:'batch',owner_id:'batch',
        owner_name:'Фотоотчёт 321',logical_bytes:4096,allocated_bytes:0,
        hardlink:true,links:2,modified_at:'2026-11-23T12:00:00Z'}
    ]
  }))
  await page.route('**/api/storage/inventory/report.csv?**',route=>
    route.fulfill({status:200,contentType:'text/csv; charset=utf-8',
      headers:{'Content-Disposition':'attachment; filename="map-file-inventory-20261123_120000.csv"'},
      body:'Путь;Размер\\r\\nPhotoSorter/data/uploads/batch/photo.jpg;4096\\r\\n'
    }))
  await page.goto('/admin')
  await page.getByRole('button',{name:'Диагностика',exact:true}).click()
  await page.getByRole('button',{name:'Открыть реестр файлов'}).click()
  await page.getByRole('button',{name:'Показать файлы'}).click()
  await expect(page.getByText('PhotoSorter/data/uploads/batch/photo.jpg')).toBeVisible()
  await expect(page.getByText('Hardlink: без повторного места')).toBeVisible()
  await expect(page.getByRole('region',{name:'Реестр файлов'})).toBeVisible()
  const download=page.waitForEvent('download')
  await page.getByRole('link',{name:'Скачать полный отчёт CSV'}).click()
  expect((await download).suggestedFilename()).toBe('map-file-inventory-20261123_120000.csv')
})

test('Administration shows host audit scope, incomplete coverage and full download',async({page})=>{
  await page.route('**/api/storage/host-audit',route=>respond(route,{
    available:true,csv_available:true,write_sites_available:true,write_sites_count:128,snapshot_id:'host-test',
    captured_at:'2026-11-23T16:00:00Z',files_scanned:120560,
    allocated_bytes:34000000000,skipped_paths:0,scan_seconds:12.4,
    scopes:{
      app:{files:40000,allocated_bytes:22000000000,logical_bytes:23000000000},
      shared_unattributed:{files:80000,allocated_bytes:12000000000,logical_bytes:15000000000},
      runtime_view:{files:560,allocated_bytes:0,logical_bytes:120000}
    },
    categories:{docker_volume:{files:1200,allocated_bytes:5000000000,logical_bytes:5000000000}},
    errors:[],limitations:['Snapshot only'],
    docker:{containers:6,volumes:3,driver:'overlay2',matched_image_layers:5,global_shared_disk_usage:[]}
  }))
  await page.route('**/api/storage/host-audit/live',route=>respond(route,{
    available:true,download_available:true,schema:'map-live-audit-v1',
    running:true,started_at:'2026-11-23T18:00:00Z',
    heartbeat_at:'2026-11-23T18:00:15Z',events:25,watched_directories:45,
    queue_overflows:0,watch_errors:0,warnings:[],limitations:[]
  }))
  await page.route('**/api/storage/host-audit/live-events.jsonl',route=>
    route.fulfill({status:200,contentType:'application/x-ndjson',headers:{
      'Content-Disposition':'attachment; filename="map-file-live-events.jsonl"'
    },body:'{"event":"create","path":"/tmp/video.part"}\n'}))
  await page.route('**/api/storage/host-audit/write-sites.csv',route=>
    route.fulfill({status:200,contentType:'text/csv',headers:{
      'Content-Disposition':'attachment; filename="map-file-write-sites.csv"'
    },body:'source_file;line;operation;effect\\nbackend/server/app.py;13;open;write\\n'}))
  await page.route('**/api/storage/host-audit/report.csv',route=>
    route.fulfill({status:200,contentType:'text/csv',headers:{
      'Content-Disposition':'attachment; filename="map-full-host-file-audit.csv"'
    },body:'path;scope\\n/srv/test;app\\n'}))
  await page.goto('/admin')
  await page.getByRole('button',{name:'Диагностика',exact:true}).click()
  await page.getByRole('button',{name:'Открыть отчёт хоста'}).click()
  const host=page.getByRole('region',{name:'Аудит сервера'})
  await expect(host.getByRole('heading',{name:'Диагностический снимок MAP'})).toBeVisible()
  await expect(host.getByText('Общие файлы Docker и системы')).toBeVisible()
  await expect(host.getByText('Временные каталоги контейнеров (только просмотр)')).toBeVisible()
  const download=page.waitForEvent('download')
  await host.getByRole('link',{name:'Скачать полный аудит сервера CSV'}).click()
  expect((await download).suggestedFilename()).toBe('map-full-host-file-audit.csv')
  await expect(host.getByText(/потенциальных мест создания.*файлов/)).toBeVisible()
  const sourceDownload=page.waitForEvent('download')
  await host.getByRole('link',{name:'Скачать карту записей файлов в коде'}).click()
  expect((await sourceDownload).suggestedFilename()).toBe('map-file-write-sites.csv')
  await expect(host.getByRole('heading',{name:'Ограниченное наблюдение файловых событий'})).toBeVisible()
  await expect(host.getByText(/Каталогов под наблюдением: 45/)).toBeVisible()
  const liveDownload=page.waitForEvent('download')
  await host.getByRole('link',{name:'Скачать события последнего сеанса JSONL'}).click()
  expect((await liveDownload).suggestedFilename()).toBe('map-file-live-events.jsonl')
})

test('storage center uses registry, drills into accounts and paginates reports',async({page})=>{
  let requests=0
  await page.route('**/api/storage/accounts?**',route=>respond(route,{
    rows:[{id:'1',username:'admin',access_role:'owner',usage:stat(250000000,350000000,2,1)},{id:'2',username:'viewer@example.test',access_role:'viewer',usage:stat(0,0,0)}],
    total:2,offset:0,limit:25,partial:false,sampled_at:'2026-11-25T00:00:00Z'
  }))
  await page.route('**/api/storage/accounts/1?**',route=>{
    requests++
    const offset=Number(new URL(route.request().url()).searchParams.get('offset'))
    return respond(route,{account:{id:'1',username:'admin',access_role:'owner'},categories:{fo_original:stat(250000000),result_media:stat(0,100000000,1,1)},
      batches:offset?[{batch_id:bid,display_name:'Последний отчёт',categories:{result_media:stat(0,100000000,1,1)}}]:Array.from({length:25},(_,i)=>({batch_id:bid.slice(0,-2)+String(i).padStart(2,'0'),display_name:'Отчёт '+i,categories:{fo_original:stat(10000000)}})),
      total:26,offset,limit:25,sampled_at:'2026-11-25T00:00:00Z',basis:'live_registry_rows_global_inode_attribution'})
  })
  await page.goto('/admin')
  const storage=page.getByRole('region',{name:'Хранилище'})
  await expect(storage.getByRole('heading',{name:'Объём хранилища'})).toBeVisible()
  await expect(storage.getByRole('img',{name:'Распределение физических блоков MAP по категориям'})).toBeVisible()
  await expect(storage.getByText('Build Cache',{exact:true})).toBeVisible()
  await expect(storage.getByText('Актуальный снимок',{exact:true})).toBeVisible()
  await storage.getByText('Фотоотчёты',{exact:true}).click()
  await expect(storage.getByText('Оригиналы ФО',{exact:false}).first()).toBeVisible()
  await storage.getByRole('button',{name:'По аккаунтам'}).click()
  await expect(storage.getByText('viewer@example.test')).toBeVisible()
  await storage.getByRole('button',{name:/admin.*Владелец/}).click()
  await expect(storage.getByRole('heading',{name:'admin'})).toBeVisible()
  await storage.getByText('Отчёт 0',{exact:true}).click()
  await expect(storage.getByRole('link',{name:'Открыть фотоотчёт'}).first()).toBeVisible()
  await storage.getByRole('button',{name:'Дальше'}).click()
  await expect(storage.getByText('Последний отчёт',{exact:true})).toBeVisible()
  expect(requests).toBe(2)
  expect(await storage.evaluate(el=>el.scrollWidth<=el.clientWidth+2)).toBeTruthy()
})
test('storage diagnostics reports stale data and errors; reconciliation and maintenance are explicit',async({page})=>{
  let reconciles=0,started=0,reads=0
  await page.route('**/api/storage/usage',route=>{
    reads++
    if(reads===2)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Сервер временно недоступен'})})
    return respond(route,storageFixture(true))
  })
  await page.route('**/api/storage/accounting/issues?**',route=>respond(route,{files:[{path:'app/unknown.bin',category:'unknown',issue:'unclassified_path',logical_bytes:2,allocated_bytes:4096}],missing:[{path:'app/users/1/lost.jpg',issue:'expected_not_observed'}],offset:0,limit:50,snapshot:'2026-11-25T00:00:00Z'}))
  await page.route('**/api/storage/reconcile',route=>{reconciles++;return respond(route,{requested_at:'2026-11-25T00:01:00Z'})})
  await page.route('**/api/storage/maintenance/expired_archives/preview',route=>respond(route,{kind:'expired_archives',files:2,allocated_bytes:4096,sampled_at:'2026-11-25T00:00:00Z',partial:true,basis:'age_based'}))
  await page.route('**/api/storage/maintenance/expired_archives',route=>{
    started++;expect(route.request().postDataJSON()).toEqual({confirmed:true})
    return respond(route,{kind:'expired_archives',state:'queued',requested_at:'2026-11-25T00:01:00Z',started_at:null,finished_at:null,removed:null,detail:null})
  })
  await page.goto('/admin')
  const storage=page.getByRole('region',{name:'Хранилище'})
  await expect(storage.getByText('Данные устарели',{exact:true})).toBeVisible()
  await storage.getByRole('button',{name:'Обновить показатели'}).click()
  await expect(storage.getByRole('alert').filter({hasText:'Сервер временно недоступен'})).toBeVisible()
  await expect(storage.getByRole('heading',{name:'Объём хранилища'})).toBeVisible()
  await storage.getByRole('button',{name:'Диагностика',exact:true}).click()
  await expect(storage.getByText('app/unknown.bin',{exact:true})).toBeVisible()
  await expect(storage.getByText('app/users/1/lost.jpg',{exact:true})).toBeVisible()
  expect(reconciles).toBe(0)
  await storage.getByRole('button',{name:'Запустить сверку'}).click()
  await expect(storage.getByText(/Дополнительная сверка поставлена/)).toBeVisible()
  expect(reconciles).toBe(1)
  await storage.getByRole('button',{name:'Обслуживание',exact:true}).click()
  await storage.getByRole('button',{name:'Предпросмотр очистки'}).first().click()
  const dialog=page.getByRole('alertdialog')
  await expect(dialog.getByText(/Кандидатов по возрасту: 2/)).toBeVisible()
  expect(started).toBe(0)
  await dialog.getByRole('button',{name:'Отмена'}).click()
  await storage.getByRole('button',{name:'Предпросмотр очистки'}).first().click()
  await page.getByRole('alertdialog').getByRole('button',{name:'Запустить очистку'}).click()
  await expect(storage.getByText(/В очереди ·/)).toBeVisible()
  expect(started).toBe(1)
})
test('storage empty and unmeasured states never fabricate capacity or history',async({page})=>{
  await page.route('**/api/storage/usage',route=>respond(route,{...storageFixture(),registry:{sampled_at:null,reconciled_at:null,partial:true,stale:true,pending_changes:0,errors:0},host:null}))
  await page.goto('/admin')
  const storage=page.getByRole('region',{name:'Хранилище'})
  await expect(storage.getByText('Ожидаем первый снимок реестра.')).toBeVisible()
  await expect(storage.getByText('Сведения Docker пока недоступны.')).toBeVisible()
  await expect(storage.getByRole('img',{name:'Распределение физических блоков MAP по категориям'})).toHaveCount(0)
})


test('storage temporary view distinguishes future bytes and observed archives; host action requires confirmation',async({page})=>{
  let confirmed=0
  const stamp='2026-11-25T00:00:00Z'
  await page.route('**/api/storage/usage',route=>{
    const data=storageFixture()
    return respond(route,{...data,registry:{...data.registry,temporary:stat(4096),reserved_bytes:2*1024**3,temporary_peak_bytes:8192,unfinished_fo:{files:3,remaining_bytes:1024**3},unfinished_references:{files:2,remaining_bytes:1024},reservations:{archive:{bytes:2*1024**3,operations:1}},temporary_operations:{rows:[],total_groups:0,partial:false}}})
  })
  await page.route('**/api/storage/operations',route=>respond(route,{active_queue:[{seq:1,kind:'media_preparation',state:'running',display_name:'Активный ФО',started_at:stamp}],io_leases:[{kind:'download',operations:1,last_seen:stamp}],archives:[{category:'zip_results',files:2,expired:1,next_eligible_at:stamp}],unfinished_fo_next_eligible_at:stamp,unfinished_reference_next_eligible_at:stamp,archive_ttl_seconds:3600,scratch_grace_seconds:3600,cleanup_worker:{alive:true,last_seen:stamp}}))
  await page.route('**/api/system/update',route=>respond(route,{available:true,busy:confirmed>0,storage_maintenance_supported:true,phase:'idle',...(confirmed?{storage_action:{kind:'storage-cache',state:'running',started_at:stamp}}:{})}))
  await page.route('**/api/storage/host-maintenance/storage-cache/preview',route=>respond(route,{kind:'storage-cache',files:5,allocated_bytes:4096,sampled_at:stamp,partial:false,basis:'typed_provider_cache_offline_only'}))
  await page.route('**/api/storage/host-maintenance/storage-cache',route=>{
    expect(route.request().postDataJSON()).toEqual({confirmed:true});confirmed++
    return respond(route,{available:true,busy:true,storage_maintenance_supported:true,storage_action:{kind:'storage-cache',state:'running',started_at:stamp}})
  })
  await page.goto('/admin')
  const storage=page.getByRole('region',{name:'Хранилище'})
  await storage.getByRole('button',{name:'Временные данные',exact:true}).click()
  await expect(storage.getByText('Активный ФО',{exact:false})).toBeVisible()
  await expect(storage.getByText('2 готовых · 1 просрочено')).toBeVisible()
  await expect(storage.getByText('ФО: 3 файлов')).toBeVisible()
  await expect(storage.getByText(/Скачивание файлов · зарегистрированных IO-операций: 1/)).toBeVisible()
  await expect(storage.getByText('Зарезервировано операциями')).toBeVisible()
  await storage.getByRole('button',{name:'Обслуживание',exact:true}).click()
  await storage.getByText('Технический кэш и закрытые журналы',{exact:true}).click()
  const button=storage.getByRole('button',{name:'Предпросмотр: Удаляемый технический кэш'})
  await button.click()
  await expect(page.getByRole('alertdialog').getByText(/Приложение будет временно остановлено/)).toBeVisible()
  expect(confirmed).toBe(0)
  await page.getByRole('alertdialog').getByRole('button',{name:'Отмена'}).click()
  await button.click()
  await page.getByRole('alertdialog').getByRole('button',{name:'Запустить очистку'}).click()
  await expect.poll(()=>confirmed).toBe(1)
  await expect(button).toBeDisabled()
})
