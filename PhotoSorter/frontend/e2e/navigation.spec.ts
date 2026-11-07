import {test,expect,Page} from '@playwright/test'
import type {Batch} from '../src/types/api'
const bid='a6d1a203-23d4-420b-a1c6-87c0f1100222'
const rid='20261105T100000-abcd1234abcd'
const pid='34b92d83-2461-4100-839f-28b7b63c9a27'
const batch={batch_id:bid,display_name:'Выезд Самара 05.11',created_at:'2026-11-05T06:00:00Z',upload_state:'sealed',thumbnail_state:'ready',delete_state:'active',photos:2,runs:1,size_bytes:2048000,pending:0}
const run={id:rid,batch_id:bid,status:'completed',models:{megaloc:{status:'completed',count:2,groups:1}},started_at:'2026-11-05T06:05:00Z',progress:{stage:'export',current:2,total:2},grouping_threshold:.5}
const photo={id:pid,name:'screen_001.jpg',bytes:1024,created_at:'2026-11-05T06:00:00Z',thumbnail_status:'pending',thumbnail_url:'/api/thumbnails/'+pid,original_url:'/api/photos/'+pid+'/original'}
const output={index:0,assigned_sam:'SAM-0001',group_id:'G0001',score:.921,thumbnail_url:'/api/thumbnails/'+pid,image_url:'/api/images/'+rid+'/megaloc/0?kind=query'}
function respond(route:any,data:unknown){return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})}
async function mock(page:Page){
  const defaults={auto_process_new_batches:false,grouping_threshold:.50,model:'megaloc'}
  await page.route(/^https?:\/\/[^/]+\/api\//,async route=>{
    const url=new URL(route.request().url()),p=url.pathname,method=route.request().method()
    if(p==='/api/auth/me')return respond(route,{username:'admin'})
    if(p==='/api/auth/login')return respond(route,{username:'admin'})
    if(p==='/api/auth/logout')return respond(route,{ok:true})
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
    if(p==='/api/storage/usage')return respond(route,{disk:{total_bytes:10000000000,used_bytes:4000000000,available_bytes:6000000000,used_fraction:.4,warning:null,reserved_bytes:600000000,admission_ok:true},categories_bytes:{photos:250000000,results:100000000}})
    if(p==='/api/system/status')return respond(route,{at:'2026-11-05T06:00:00Z',worker:{queue:{},expected_threads:7},thumbnails:{queued:0},disk:{total_bytes:10000000000,available_bytes:6000000000,reserved_bytes:600000000},api:{uptime_seconds:400,latency:{samples:6,p50_ms:13,p95_ms:30},rss_peak_kib:90000}})
    if(p==='/api/logs/usage')return respond(route,{bytes:2000,budget_bytes:524288000})
    if(p==='/api/logs/'+rid+'/page')return respond(route,{events:[{at:'2026-11-05T06:02:00Z',level:'INFO',model:'megaloc',source:'MegaLoc',message:'Обработка завершена'}],next_cursor:null})
    if(p.includes('/api/thumbnails/'))return route.fulfill({status:202,contentType:'application/json',body:'{"detail":"pending"}'})
    return route.fulfill({status:404,contentType:'application/json',body:JSON.stringify({detail:'Unexpected test API: '+p})})
  })
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
test('FO gallery is separate and shows real original viewer',async({page})=>{
  await page.goto('/fo/'+bid)
  await expect(page.getByRole('heading',{name:'Выезд Самара 05.11'})).toBeVisible()
  await expect(page.getByText('Подготовка миниатюр').first()).toBeVisible()
  await page.getByRole('button',{name:'Открыть screen_001.jpg'}).click()
  await expect(page.getByRole('dialog',{name:'Просмотр фотографии'})).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog',{name:'Просмотр фотографии'})).not.toBeVisible()
})
test('full ZIP confirmation is separate from download with required phrase',async({page})=>{
  await page.goto('/results/'+rid)
  await expect(page.getByRole('heading',{name:'Выезд Самара 05.11'})).toBeVisible()
  const save=page.getByRole('button',{name:'Я сохранил полный архив'})
  await save.click()
  const confirm=page.getByRole('button',{name:'Подтвердить сохранение ZIP'})
  await expect(confirm).toBeDisabled()
  await page.getByRole('textbox',{name:/СОХРАНЁН/}).fill('СОХРАНЁН')
  await expect(confirm).toBeEnabled()
  await confirm.click()
  await expect(page.getByText('Архив подтверждён')).toBeVisible()
})
test('auto-processing preference defaults off and saves on the server',async({page})=>{
  await page.goto('/settings')
  await page.getByRole('button',{name:/MegaLoc и CPU/}).click()
  const enabled=page.getByRole('checkbox',{name:'Автоматически обрабатывать загруженные ФО'})
  await expect(enabled).not.toBeChecked()
  await enabled.check()
  await expect(enabled).toBeChecked()
  await page.reload()
  await page.getByRole('button',{name:/MegaLoc и CPU/}).click()
  await expect(enabled).toBeChecked()
})
test('theme setting works in light and dark',async({page})=>{
  await page.goto('/settings')
  await page.getByRole('radio',{name:'Светлая'}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','light')
  await page.getByRole('radio',{name:'Тёмная'}).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark')
})
test('mobile drawer allows navigation',async({page,isMobile})=>{
  test.skip(!isMobile,'Mobile layout only')
  await page.goto('/fo')
  await page.getByRole('button',{name:'Открыть меню'}).click()
  await page.getByRole('link',{name:'Настройки'}).click()
  await expect(page.getByRole('heading',{name:'Настройки',exact:true})).toBeVisible()
})

test('processing overview moved to Settings, run details live under Queue',async({page})=>{
  await page.goto('/settings')
  await page.getByRole('button',{name:/MegaLoc и CPU/}).click()
  await expect(page.getByRole('heading',{name:'MegaLoc',exact:true})).toBeVisible()
  await expect(page.getByText('Модель установлена')).toBeVisible()
  await expect(page.getByRole('slider',{name:'Число потоков CPU для MegaLoc'})).toBeVisible()
  await page.goto('/queue/runs/'+rid)
  await expect(page.getByRole('heading',{name:'Выезд Самара 05.11'})).toBeVisible()
  await expect(page.getByRole('link',{name:'История очереди'})).toBeVisible()
  await page.goto('/processing')
  await expect(page).toHaveURL(/\/fo$/)
})
test('FO upload opens a global dialog that can be minimized without unmounting',async({page})=>{
  await page.goto('/fo')
  await page.getByRole('button',{name:'+ Загрузить папку'}).click()
  const dialog=page.getByRole('dialog',{name:'Загрузить папку фотографий'})
  await expect(dialog).toBeVisible()
  await page.getByRole('button',{name:'Свернуть загрузку'}).click()
  await expect(dialog).toBeHidden()
  await page.getByRole('button',{name:/Загрузка ФО/}).click()
  await expect(dialog).toBeVisible()
})
test('construction list remains one line with ellipsis and a separate count',async({page,isMobile})=>{
  test.skip(isMobile,'Desktop split list only')
  const longName='SAM 0001 — Московское шоссе, 19 километр, улица Очень Длинная, дом 28А корпус 7'
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

test('desktop construction list can be resized and the width survives refresh',async({page,isMobile})=>{
  test.skip(isMobile,'Mobile uses the standard picker')
  await page.goto('/references')
  const aside=page.locator('.split-aside')
  const grip=page.getByRole('separator',{name:'Изменить ширину списка конструкций'})
  await expect(grip).toBeVisible()
  const before=await aside.evaluate(el=>el.getBoundingClientRect().width)
  const box=await grip.boundingBox()
  expect(box).not.toBeNull()
  if(!box)throw Error('Resize grip is missing')
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2)
  await page.mouse.down()
  await page.mouse.move(box.x+box.width/2+120,box.y+box.height/2,{steps:6})
  await page.mouse.up()
  const after=await aside.evaluate(el=>el.getBoundingClientRect().width)
  expect(after).toBeGreaterThan(before+50)
  const saved=await page.evaluate(()=>localStorage.getItem('ps.group-picker.width'))
  expect(saved).toBe(String(Math.round(after)))
  await page.reload()
  await expect(aside).toBeVisible()
  const restored=await aside.evaluate(el=>el.getBoundingClientRect().width)
  expect(Math.abs(restored-after)).toBeLessThan(2)
  await grip.focus()
  await page.keyboard.press('ArrowLeft')
  const narrower=await aside.evaluate(el=>el.getBoundingClientRect().width)
  expect(narrower).toBeLessThan(restored)
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
  await expect(page.getByText('Очередь пуста')).toBeVisible()
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
  await expect.poll(()=>started).toBe(1)
  await expect(card.getByText('№3 в очереди')).toBeVisible()
  await card.getByRole('button',{name:'Убрать из очереди'}).click()
  await page.getByRole('alertdialog').getByRole('button',{name:'Убрать из очереди'}).click()
  await expect.poll(()=>stopped).toBe(1)
  await expect(card.locator('.task-card-status')).toHaveText('Остановлено')
  await expect(card.getByRole('button',{name:'Повторить'})).toBeVisible()
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
  await page.goto('/settings')
  await page.getByRole('button',{name:/Система/}).click()
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

test('staged reference upload remains available during active FO and uses manifest API',async({page})=>{
  const status={
    unified_queue_enabled:true,staged_imports_enabled:true,baseline_state:'ready',
    current_version:12,current_version_id:12,published_references:1,
    published_at:'2026-11-06T09:00:00Z',notice:false,pending_changes:0,
    notice_version_id:null
  }
  const source=Buffer.from('test reference image bytes for staged import')
  let registered:any=null,finished=false,queued=0
  await page.route('**/api/reference-library/status',route=>respond(route,status))
  await page.route(/^https?:\/\/[^/]+\/api\/runs(?:\?.*)?$/,route=>
    respond(route,{runs:[{...run,status:'running'}],total:1}))
  await page.route(/^https?:\/\/[^/]+\/api\/reference-imports(?:\/.*)?(?:\?.*)?$/,route=>{
    const url=new URL(route.request().url())
    const path=url.pathname
    const method=route.request().method()
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
  await page.goto('/references')
  const uploadButton=page.getByRole('button',{name:'+ Загрузить образцы'})
  await expect(uploadButton).toBeEnabled()
  await uploadButton.click()
  await page.getByRole('tab',{name:'Фото в конструкцию'}).click()
  await page.locator('.upload-drop input[type="file"]').setInputFiles({
    name:'new.jpg',mimeType:'image/jpeg',buffer:source
  })
  await page.getByRole('button',{name:'Добавить фото',exact:true}).click()
  await expect.poll(()=>queued).toBe(1)
  expect(finished).toBe(true)
  expect(registered.sam).toBe('SAM-0001')
  expect(registered.size).toBe(source.length)
  expect(registered.sha256).toMatch(/^[0-9a-f]{64}$/)
  await expect(page.getByText('Файлы приняты. Подготовка образцов поставлена в очередь.')).toBeVisible()
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
