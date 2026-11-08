import {test,expect} from '@playwright/test'
const sam='SAM 0001',id='34b92d83-2461-4100-839f-28b7b63c9a27'
const photo={id,name:'screen_001.jpg',bytes:1024,created_at:'2026-11-08T00:00:00Z',
  thumbnail_status:'pending',original_url:'/api/photos/'+id+'/original'}
const image='<svg xmlns="http://www.w3.org/2000/svg" width="800" height="500"><rect width="800" height="500" fill="#333"/><rect x="170" y="100" width="460" height="300" fill="#15803d"/></svg>'
test('create and edit a persistent four-corner annotation in reference viewer',async({page,isMobile})=>{
  const screens:Array<{id:string;name:string;annotations:Array<Record<string,unknown>>}>=[]
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url()),path=decodeURIComponent(url.pathname),method=route.request().method()
    const json=(obj:unknown,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(obj)})
    if(path==='/api/auth/me')return json({username:'admin'})
    if(path==='/api/references')return json({sam:[{sam,photos:1,display_name:'SAM 0001 — Гагарина 64'}],total:1})
    if(path==='/api/references/'+sam+'/photos')return json({photos:[photo],next_cursor:null})
    if(path==='/api/references/'+sam+'/screens')return json({screens})
    if(path==='/api/references/'+sam+'/photos/'+id+'/screen-metadata')
      return json({reference_id:id,width:800,height:500,source_sha256:'valid'})
    if(path==='/api/photos/'+id+'/original')
      return route.fulfill({status:200,contentType:'image/svg+xml',body:image})
    if(path==='/api/references/'+sam+'/screen-annotations'&&method==='POST'){
      const body=JSON.parse(route.request().postData()||'{}')
      const sid=body.screen_id||'ab712800-0000-4000-8000-000000000001'
      let screen=screens.find(s=>s.id===sid)
      if(!screen){screen={id:sid,name:body.screen_name,annotations:[]};screens.push(screen)}
      const a={id:'bb712800-0000-4000-8000-000000000001',reference_id:id,
        corners:body.corners,band_width_px:body.band_width_px,version:1,
        image_width:800,image_height:500,source_sha256:'valid'}
      screen.annotations.push(a)
      return json({id:a.id,screen_id:sid,version:1},201)
    }
    if(path.includes('/screen-annotations/')&&method==='PATCH'){
      const body=JSON.parse(route.request().postData()||'{}')
      const a=screens[0]?.annotations[0]
      if(!a)return json({detail:'missing'},404)
      a.corners=body.corners;a.band_width_px=body.band_width_px;a.version=2
      return json({id:a.id,screen_id:screens[0].id,version:2})
    }
    if(path.startsWith('/api/thumbnails/'))return json({detail:'pending'},202)
    return json({})
  })
  await page.goto('/references')
  await page.getByRole('button',{name:'Открыть screen_001.jpg'}).click()
  await page.getByRole('button',{name:'Выделить экран'}).click()
  const dialog=page.getByRole('dialog',{name:'Разметка экрана'})
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('circle')).toHaveCount(4)
  const first=dialog.locator('circle').first()
  const initialX=Number(await first.getAttribute('cx'))
  if(!isMobile){
    const box=await first.boundingBox()
    expect(box).not.toBeNull()
    const x=box!.x+box!.width/2,y=box!.y+box!.height/2
    await page.mouse.move(x,y)
    await page.mouse.down()
    await page.mouse.move(x+24,y+8,{steps:5})
    await page.mouse.up()
    expect(Number(await first.getAttribute('cx'))).not.toBe(initialX)
  }
  await dialog.getByRole('textbox',{name:'Название экрана'}).fill('Основной LED')
  await dialog.getByRole('button',{name:'Сохранить разметку'}).click()
  await expect(dialog).not.toBeVisible()
  expect(screens).toHaveLength(1)
  if(!isMobile)expect((screens[0].annotations[0].corners as Array<{x:number;y:number}>)[0].x).not.toBe(initialX)
  await page.reload()
  await page.getByRole('button',{name:'Открыть screen_001.jpg'}).click()
  await page.getByRole('button',{name:'Выделить экран'}).click()
  await dialog.getByRole('combobox',{name:'Экран конструкции'}).click()
  await dialog.getByRole('option',{name:/Основной LED/}).click()
  await expect(dialog.getByText('Версия: 1')).toBeVisible()
  await dialog.getByRole('button',{name:'Сохранить разметку'}).click()
  await expect(dialog).not.toBeVisible()
  expect(screens[0].annotations[0].version).toBe(2)
})
