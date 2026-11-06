import {test,expect,Page} from '@playwright/test'
const bid='a6d1a203-23d4-420b-a1c6-87c0f1100222'
const rid='20261105T100000-abcd1234abcd'
const pid='34b92d83-2461-4100-839f-28b7b63c9a27'
const batch={batch_id:bid,display_name:'Выезд Самара 05.11',created_at:'2026-11-05T06:00:00Z',upload_state:'sealed',thumbnail_state:'ready',delete_state:'active',photos:2,runs:1,size_bytes:2048000,pending:0}
const run={id:rid,batch_id:bid,status:'completed',models:{megaloc:{status:'completed',count:2,groups:1}},started_at:'2026-11-05T06:05:00Z',progress:{stage:'export',current:2,total:2},grouping_threshold:.5}
const photo={id:pid,name:'screen_001.jpg',bytes:1024,created_at:'2026-11-05T06:00:00Z',thumbnail_status:'pending',thumbnail_url:'/api/thumbnails/'+pid,original_url:'/api/photos/'+pid+'/original'}
const output={index:0,assigned_sam:'SAM-0001',group_id:'G0001',score:.921,thumbnail_url:'/api/thumbnails/'+pid,image_url:'/api/images/'+rid+'/megaloc/0?kind=query'}
function respond(route:any,data:unknown){return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})}
async function mock(page:Page){
  await page.route(/^https?:\/\/[^/]+\/api\//,async route=>{
    const url=new URL(route.request().url()),p=url.pathname,method=route.request().method()
    if(p==='/api/auth/me')return respond(route,{username:'admin'})
    if(p==='/api/auth/login')return respond(route,{username:'admin'})
    if(p==='/api/auth/logout')return respond(route,{ok:true})
    if(p==='/api/batches')return respond(route,{batches:[batch],total:1})
    if(p==='/api/batches/'+bid)return respond(route,batch)
    if(p==='/api/batches/'+bid+'/gallery')return respond(route,{photos:[photo],next_cursor:null})
    if(p==='/api/thumbnails/status/'+bid+'/counts')return respond(route,{total:2,ready:2,failed:0})
    if(p==='/api/batches/'+bid+'/retention')return respond(route,{batch_id:bid,delete_state:'active',warning:false,download_confirmed_at:null,delete_after_at:null})
    if(p==='/api/batches/'+bid+'/downloads/confirm'&&method==='POST')return respond(route,{batch_id:bid,download_confirmed_at:'2026-11-05T06:50:00Z',delete_after_at:'2027-01-05T06:50:00Z',confirmed_run_id:rid})
    if(p==='/api/references')return respond(route,{sam:[{sam:'SAM-0001',photos:1}],total:1})
    if(p==='/api/references/cache/status')return respond(route,{total:1,cached:1,current_signature:null})
    if(p==='/api/references/SAM-0001/photos')return respond(route,{photos:[photo],next_cursor:null})
    if(p==='/api/runs')return respond(route,{runs:[run],total:1})
    if(p==='/api/runs/'+rid)return respond(route,run)
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
  await expect(page.getByText('Выезд Самара 05.11').first()).toBeVisible()
  for(const [path,heading] of [['/references','Образцы'],['/processing','Обработка'],['/results','Результаты'],['/logs','Логи'],['/settings','Настройки']] as const){
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

test('processing select includes fresh and previously processed completed batches',async({page})=>{
  await page.goto('/processing')
  const select=page.getByRole('combobox',{name:'Партия ФО'})
  // The baseline fixture has one completed run. Re-running it is allowed by the API.
  await expect(select).toContainText('Выезд Самара 05.11')
  await expect(page.getByRole('button',{name:/Запустить \/ поставить в очередь/})).toBeEnabled()
  await select.click()
  await expect(page.getByRole('listbox',{name:'Партия ФО'})).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('listbox',{name:'Партия ФО'})).not.toBeVisible()
  await expect(select).toHaveAttribute('aria-expanded','false')

  // An older API response may omit runs for an entirely new batch.
  await page.route(/^https?:\/\/[^/]+\/api\/batches(?:\?.*)?$/,route=>
    respond(route,{batches:[{...batch,runs:undefined}],total:1}))
  await page.reload()
  await expect(select).toContainText('Выезд Самара 05.11')
  await expect(page.getByRole('button',{name:/Запустить \/ поставить в очередь/})).toBeEnabled()
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
  await expect(page.locator('.sidebar .nav-link').first()).toHaveAttribute('title','ФО')
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
