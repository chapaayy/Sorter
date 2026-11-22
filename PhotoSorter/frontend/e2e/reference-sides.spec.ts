import {test,expect} from '@playwright/test'

const sam='SAM 0001'
const id1='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const id2='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const photos=[
  {id:id1,name:'IMG_001.jpg',bytes:1024,created_at:'2026-11-22T07:00:00Z',
   thumbnail_status:'ready',thumbnail_url:'/api/thumbnails/'+id1,
   original_url:'/api/photos/'+id1+'/original'},
  {id:id2,name:'IMG_002.jpg',bytes:1024,created_at:'2026-11-22T07:00:01Z',
   thumbnail_status:'ready',thumbnail_url:'/api/thumbnails/'+id2,
   original_url:'/api/photos/'+id2+'/original'},
]

test('reference sides: select, assign, group, preview and queued deletion',async({page})=>{
  const sides=new Map<string,string|null>([[id1,null],[id2,'А']])
  let updateCount=0,queued=false
  await page.route(/^https?:\/\/[^/]+\/api\//,async route=>{
    const url=new URL(route.request().url())
    const pathname=decodeURIComponent(url.pathname)
    const method=route.request().method()
    const json=(value:unknown)=>route.fulfill({
      status:200,contentType:'application/json',body:JSON.stringify(value)})
    if(pathname==='/api/auth/me')return json({username:'admin'})
    if(pathname==='/api/references')return json({
      sam:[{sam,photos:2,display_name:'SAM 0001 — Победы 12'}],total:2})
    if(pathname==='/api/references/'+sam+'/photos')return json({
      photos:photos.map(p=>({...p,side:sides.get(p.id)})),next_cursor:null})
    if(pathname==='/api/references/'+sam+'/sides'&&method==='PATCH'){
      const payload=route.request().postDataJSON()
      for(const id of payload.photo_ids)sides.set(id,payload.side)
      updateCount++
      return json({updated:payload.photo_ids.length,side:payload.side})
    }
    if(pathname==='/api/references/files/'+id2&&method==='DELETE'){
      queued=true;return json({queued:true,task_id:'cccccccc-cccc-4ccc-8ccc-cccccccccccc'})
    }
    if(pathname==='/api/reference-library/status')return json({baseline_state:'ready',current_version:1,
      published_references:2,notice:false,pending_changes:0})
    if(pathname==='/api/reference-library/events')return json({events:[]})
    if(pathname==='/api/work-queue')return json({tasks:[],total:0})
    if(pathname.startsWith('/api/thumbnails/'))return route.fulfill({status:202,body:''})
    if(pathname.startsWith('/api/photos/'))return route.fulfill({status:404,body:''})
    return json({})
  })
  await page.goto('/references')
  await expect(page.getByText('Неназначена сторона')).toBeVisible()
  await expect(page.getByText('Сторона А',{exact:true})).toBeVisible()
  await expect(page.locator('.photo-item.photo-unassigned')).toHaveCount(1)
  const before=await page.getByRole('button',{name:'Открыть IMG_001.jpg'}).boundingBox()
  await expect(page.getByRole('button',{name:'Выбрать IMG_001.jpg'})).toHaveCount(0)
  await page.getByRole('button',{name:'Выделить',exact:true}).click()
  const after=await page.getByRole('button',{name:'Выбрать IMG_001.jpg'}).boundingBox()
  expect(before?.y).toBeCloseTo(after?.y??0,0)
  await expect(page.getByRole('toolbar',{name:'Работа с выделенными образцами'})).toBeVisible()
  await page.getByRole('button',{name:'Выбрать IMG_001.jpg'}).click()
  await expect(page.getByText('Выбрано: 1')).toBeVisible()
  await page.getByRole('button',{name:'Снять выделение'}).click()
  await expect(page.getByText('Выбрано: 0')).toBeVisible()
  await page.getByRole('button',{name:'Выделить все'}).click()
  await expect(page.getByText('Выбрано: 2')).toBeVisible()
  await page.getByRole('button',{name:'Выбрать IMG_002.jpg'}).click()
  await expect(page.getByText('Выбрано: 1')).toBeVisible()
  await page.getByRole('button',{name:'Назначить сторону'}).click()
  const dialog=page.getByRole('dialog',{name:'Назначить сторону'})
  await dialog.getByRole('textbox',{name:'Название стороны'}).fill('Б')
  await dialog.getByRole('button',{name:'Назначить',exact:true}).click()
  await expect.poll(()=>updateCount).toBe(1)
  await expect(page.getByText('Сторона Б',{exact:true})).toBeVisible()
  await expect(page.locator('.photo-item.photo-unassigned')).toHaveCount(0)
  await page.getByRole('button',{name:'Готово',exact:true}).click()
  await expect(page.getByRole('toolbar',{name:'Работа с выделенными образцами'})).toHaveCount(0)
  await page.getByRole('button',{name:'Открыть IMG_001.jpg'}).click()
  const viewer=page.getByRole('dialog',{name:'Просмотр фотографии'})
  await expect(viewer).toBeVisible()
  await viewer.getByRole('button',{name:'Увеличить'}).click()
  await expect(viewer.getByText('150%')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(viewer).toHaveCount(0)
  await page.getByRole('button',{name:'Удалить IMG_002.jpg'}).click()
  await page.getByRole('alertdialog').getByRole('button',{name:'Удалить Образец'}).click()
  await expect.poll(()=>queued).toBe(true)
  await expect(page.getByText('Удаление поставлено в очередь')).toBeVisible()
})

// Select all must include the unscrolled pages, not only the first 60 tiles.
test('select all reaches subsequent reference gallery pages',async({page})=>{
  const makePhoto=(index:number)=>({
    id:'reference-'+index,name:'IMG_'+String(index).padStart(4,'0')+'.jpg',
    bytes:1024,created_at:'2026-11-22T07:00:00Z',
    thumbnail_status:'pending',side:null
  })
  const first=Array.from({length:60},(_,index)=>makePhoto(index+1))
  const rest=[makePhoto(61),makePhoto(62)]
  let nextPageRequests=0
  await page.route(/^https?:\/\/[^/]+\/api\//,async route=>{
    const pathname=decodeURIComponent(new URL(route.request().url()).pathname)
    const url=new URL(route.request().url())
    const json=(body:unknown)=>route.fulfill({
      status:200,contentType:'application/json',body:JSON.stringify(body)})
    if(pathname==='/api/auth/me')return json({username:'admin'})
    if(pathname==='/api/references')return json({
      sam:[{sam,photos:62,display_name:'SAM 0001 — Победы 12'}],total:62})
    if(pathname==='/api/references/'+sam+'/photos'){
      if(url.searchParams.get('cursor')){
        nextPageRequests++
        return json({photos:rest,next_cursor:null})
      }
      return json({photos:first,next_cursor:'second-page'})
    }
    if(pathname==='/api/reference-library/status')return json({baseline_state:'ready'})
    if(pathname==='/api/reference-library/events')return json({events:[]})
    return json({})
  })
  await page.goto('/references')
  await expect(page.getByText('Неназначена сторона')).toBeVisible()
  await page.getByRole('button',{name:'Выделить',exact:true}).click()
  await page.getByRole('button',{name:'Выделить все'}).click()
  await expect(page.getByText('Выбрано: 62')).toBeVisible()
  expect(nextPageRequests).toBeGreaterThanOrEqual(1)
  await page.getByRole('button',{name:'Снять выделение'}).click()
  await expect(page.getByText('Выбрано: 0')).toBeVisible()
})
