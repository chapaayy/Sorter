import {test,expect} from '@playwright/test'

test('manual processing requires explicit region chips and sends selected codes',async({page})=>{
  const batches=[{
    batch_id:'11111111-1111-4111-8111-111111111111',
    display_name:'Фотоотчёт SAM и SZR',created_at:'2026-11-23T00:00:00Z',
    delete_state:'active',upload_state:'complete',upload_manifest_state:'complete',
    photos:10,videos:0,size_bytes:30000,pending:0,runs:0,latest_run:null
  }]
  let submitted:string[]|null=null
  await page.route(/^https?:\/\/[^/]+\/api\//,route=>{
    const url=new URL(route.request().url()),path=decodeURIComponent(url.pathname)
    const json=(body:unknown)=>route.fulfill({status:200,contentType:'application/json',
      body:JSON.stringify(body)})
    if(path==='/api/auth/me')return json({username:'admin'})
    if(path==='/api/batches')return json({batches,total:1})
    if(path==='/api/work-queue')return json({tasks:[],total:0})
    if(path==='/api/regions')return json({regions:[
      {code:'SAM',constructions:5},{code:'SZR',constructions:3},{code:'TLT',constructions:2}]})
    if(path==='/api/runs'&&route.request().method()==='POST'){
      const input=route.request().postDataJSON()
      submitted=input.regions
      return json({id:'test-region-run',batch_id:batches[0]!.batch_id,
        status:'queued',queue_position:1,selected_regions:input.regions})
    }
    return json({})
  })
  await page.goto('/fo')
  await page.getByRole('button',{name:'Обработать',exact:true}).click()
  const dialog=page.getByRole('dialog',{name:'Выбор регионов для обработки'})
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button',{name:'Обработать'})).toBeDisabled()
  await dialog.getByRole('button',{name:'SAM'}).click()
  await dialog.getByRole('button',{name:'SZR'}).click()
  await expect(dialog.getByRole('button',{name:'SAM'})).toHaveAttribute('aria-pressed','true')
  await expect(dialog.getByRole('button',{name:'TLT'})).toHaveAttribute('aria-pressed','false')
  await dialog.getByRole('button',{name:'Обработать'}).click()
  await expect.poll(()=>submitted).toEqual(['SAM','SZR'])
})
