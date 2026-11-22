import {test,expect} from '@playwright/test'

const email='viewer@example.test', password='example-only-passphrase'
const run='20261114T170000-0123456789ab'
const item={id:'00000000-0000-4000-8000-000000000001',email,comment:'Я из отдела рекламы. Нужны готовые фотоотчёты.',
  status:'pending',created_at:'2026-11-14T17:00:00Z',decided_at:null}

test('login and registration use the saved MAP theme',async({page})=>{
  await page.route('**/api/auth/me',route=>route.fulfill({status:401,json:{detail:'Необходим вход'}}))
  await page.addInitScript(()=>localStorage.setItem('ps.theme',location.pathname==='/login'?'dark':'light'))
  await page.emulateMedia({colorScheme:'light'})
  await page.goto('/login')
  const surface=page.locator('.auth-page')
  await expect(surface).toHaveCSS('background-color','rgb(16, 16, 16)')
  await expect(page.locator('body')).toHaveCSS('background-color','rgb(16, 16, 16)')
  await page.emulateMedia({colorScheme:'dark'})
  await page.goto('/register')
  await expect(surface).toHaveCSS('background-color','rgb(250, 250, 250)')
  await expect(page.locator('body')).toHaveCSS('background-color','rgb(250, 250, 250)')
})

test('a cookie restores the same page after reload and temporary session-check failure',async({page})=>{
  const cookie='photosorter_session=test-token'
  let unavailable=false,expired=false
  await page.route(url=>url.pathname.startsWith('/api/'),async route=>{
    const path=new URL(route.request().url()).pathname
    if(path==='/api/auth/login')return route.fulfill({
      headers:{'set-cookie':cookie+'; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800'},
      json:{username:email}
    })
    if(path==='/api/auth/me'){
      if(unavailable)return route.fulfill({status:503,json:{detail:'Временно недоступно'}})
      // WebKit's Playwright interception can omit Cookie from the synthetic
      // request headers. Inspect the browser context cookie jar directly.
      const stored=await page.context().cookies(route.request().url())
      if(!expired&&stored.some(c=>c.name==='photosorter_session'&&c.value==='test-token'))
        return route.fulfill({json:{username:email}})
      return route.fulfill({status:401,json:{detail:'Необходим вход'}})
    }
    if(path==='/api/results/catalog')return route.fulfill({json:{items:[],has_more:false}})
    return route.fulfill({status:404,json:{detail:'Не найдено'}})
  })
  await page.goto('/results')
  await expect(page).toHaveURL(/\/login\?next=/)
  await page.getByLabel('Электронная почта или логин').fill(email)
  await page.locator('input[autocomplete="current-password"]').fill(password)
  await page.getByRole('button',{name:'Продолжить',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Результаты'})).toBeVisible()
  // Playwright's synthetic Set-Cookie response is not always persisted by
  // WebKit. Seed the same server cookie through the browser context so this
  // regression test exercises reload/session-check behavior deterministically.
  await page.context().addCookies([{
    name:'photosorter_session',value:'test-token',url:new URL(page.url()).origin,
    httpOnly:true,sameSite:'Strict'
  }])
  await expect.poll(async()=> (await page.context().cookies())
    .find(c=>c.name==='photosorter_session')?.value).toBe('test-token')
  await page.reload()
  await expect(page.getByRole('heading',{name:'Результаты'})).toBeVisible()
  unavailable=true
  await page.reload()
  await expect(page.getByRole('alert')).toContainText('Не удалось проверить сессию')
  await expect(page).toHaveURL(/\/results$/)
  await expect(page.getByRole('heading',{name:'Войти в MAP'})).toHaveCount(0)
  unavailable=false
  await page.getByRole('button',{name:'Повторить',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Результаты'})).toBeVisible()
  expired=true
  await page.reload()
  await expect(page.getByRole('heading',{name:'Войти в MAP'})).toBeVisible()
})

test('password caption transitions on focus and holds position with a value',async({page})=>{
  await page.route('**/api/auth/me',route=>route.fulfill({status:401,json:{detail:'Необходим вход'}}))
  await page.emulateMedia({reducedMotion:'no-preference'})
  await page.goto('/login')
  await expect(page).toHaveTitle('MAP')
  await expect(page.getByRole('heading',{name:'Войти в MAP'})).toBeVisible()
  const field=page.locator('.auth-field').filter({has:page.locator('input[autocomplete="current-password"]')})
  const caption=field.locator('.auth-field-caption')
  await expect(caption).toHaveCSS('transition-property','transform')
  await expect(caption).toHaveCSS('transition-duration','0.08s')
  await expect(caption).toHaveCSS('transition-timing-function','ease-in-out')
  const motion=await caption.evaluate(async node=>{
    const input=node.closest('label')!.querySelector('input')!
    const initialY=node.getBoundingClientRect().top
    input.focus()
    const animations=node.getAnimations()
    await Promise.all(animations.map(animation=>animation.finished))
    return {lift:initialY-node.getBoundingClientRect().top,animated:animations.length>0}
  })
  expect(motion.animated).toBe(true)
  expect(motion.lift).toBeCloseTo(26)
  await field.locator('input').fill(password)
  await field.locator('input').blur()
  await expect(caption).not.toHaveCSS('transform','none')
  await field.locator('input').fill('')
  await field.locator('input').blur()
  await expect(caption).toHaveCSS('transform','none')
  await page.emulateMedia({reducedMotion:'reduce'})
  await expect(caption).toHaveCSS('transition-property','none')
})

test('pill fields, password toggle and registration feedback',async({page})=>{
  await page.route('**/api/auth/me',route=>route.fulfill({status:401,json:{detail:'Необходим вход'}}))
  let sent=0
  await page.route('**/api/auth/register',route=>{
    sent++
    expect(route.request().postDataJSON()).toEqual({email,password,confirmation:password,comment:item.comment})
    return route.fulfill({status:202,json:{status:'received'}})
  })
  await page.goto('/login')
  const input=page.getByLabel('Электронная почта или логин')
  await input.fill('admin')
  await expect(input).toHaveCSS('text-align','center')
  const pass=page.locator('input[autocomplete="current-password"]')
  await pass.fill(password)
  await page.getByRole('button',{name:'Показать пароль',exact:true}).click()
  await expect(pass).toHaveAttribute('type','text')
  await page.getByRole('button',{name:'Скрыть пароль',exact:true}).click()
  await expect(pass).toHaveAttribute('type','password')
  await expect(page.getByText('Редактировать')).toHaveCount(0)

  await page.getByRole('link',{name:'Зарегистрироваться'}).click()
  await expect(page).toHaveURL(/\/register$/)
  await page.locator('input[type=email]').fill(email)
  const passwords=page.locator('input[autocomplete="new-password"]')
  await passwords.nth(0).fill(password)
  await passwords.nth(1).fill('different-example-passphrase')
  await page.getByLabel('О себе и нужном доступе').fill(item.comment)
  await page.getByRole('button',{name:'Отправить на модерацию'}).click()
  await expect(page.getByRole('alert')).toHaveText('Пароли не совпадают.')
  expect(sent).toBe(0)
  await passwords.nth(1).fill(password)
  await page.getByRole('button',{name:'Отправить на модерацию'}).click()
  await expect(page.getByRole('heading',{name:'Заявка отправлена'})).toBeVisible()
  await page.getByRole('link',{name:'Вернуться ко входу'}).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('owner can read the comment and approve after confirmation',async({page})=>{
  await page.route('**/api/auth/me',route=>route.fulfill({json:{username:'admin'}}))
  await page.route('**/api/admin/users?**',route=>route.fulfill({json:{items:[],has_more:false}}))
  let decided=false
  await page.route('**/api/results/catalog**',route=>route.fulfill({
    json:{items:[{id:run,display_name:'Готовый отчёт',status:'completed'}],has_more:false}
  }))
  await page.route('**/api/admin/access-requests**',route=>{
    if(route.request().method()==='POST'){
      expect(route.request().postDataJSON()).toEqual({approved:true,run_ids:[run]})
      decided=true
      return route.fulfill({json:{...item,status:'approved'}})
    }
    if(new URL(route.request().url()).pathname.endsWith('/grants')){
      if(route.request().method()==='PUT'){
        expect(route.request().postDataJSON()).toEqual({run_ids:[]})
        return route.fulfill({json:{items:[]}})
      }
      return route.fulfill({json:{items:[{id:run,display_name:'Готовый отчёт',status:'completed'}]}})
    }
    const status=new URL(route.request().url()).searchParams.get('status')
    return route.fulfill({json:{items:decided?(status==='approved'?[{...item,status:'approved'}]:[]):[item],has_more:false}})
  })
  await page.goto('/settings')
  await expect(page.getByRole('heading',{name:'О сервисе MAP'})).toBeVisible()
  await expect(page.getByText('Match, Assign, Package',{exact:true})).toBeVisible()
  await page.goto('/admin')
  await expect(page.getByRole('heading',{name:'Администрирование'})).toBeVisible()
  await expect(page.getByText(item.comment)).toBeVisible()
  await page.getByRole('button',{name:'Одобрить',exact:true}).click()
  const dialog=page.getByRole('dialog',{name:'Выдать доступ к результатам'})
  await dialog.getByRole('checkbox',{name:/Готовый отчёт/}).check()
  await dialog.getByRole('button',{name:'Одобрить'}).click()
  await expect(page.getByText('Заявок пока нет.')).toBeVisible()
  await page.getByRole('button',{name:'Одобренные'}).click()
  await expect(page.getByText(email,{exact:true})).toBeVisible()
  await page.getByRole('button',{name:'Изменить доступ'}).click()
  await expect(dialog.getByRole('checkbox',{name:/Готовый отчёт/})).toBeChecked()
  await dialog.getByRole('checkbox',{name:/Готовый отчёт/}).uncheck()
  await dialog.getByRole('button',{name:'Сохранить'}).click()
  await expect(page.getByText('Доступ обновлён')).toBeVisible()
})

test('approved viewer lands in Results and sees no edit controls',async({page})=>{
  const unexpected:string[]=[]
  await page.route(url=>url.pathname.startsWith('/api/'),route=>{
    const path=new URL(route.request().url()).pathname
    if(path==='/api/auth/me')return route.fulfill({json:{username:email}})
    if(path==='/api/results/catalog')return route.fulfill({json:{items:[{id:run,display_name:'Готовый отчёт',status:'completed'}],has_more:false}})
    if(path==='/api/results/'+run)return route.fulfill({json:{id:run,display_name:'Готовый отчёт',status:'completed'}})
    if(path.endsWith('/sam'))return route.fulfill({json:{'SAM-0001':1}})
    if(path.endsWith('/groups'))return route.fulfill({json:{}})
    if(path.endsWith('/photos'))return route.fulfill({json:{photos:[],next_cursor:null}})
    unexpected.push(path)
    return route.fulfill({status:403,json:{detail:'Недостаточно прав'}})
  })
  await page.goto('/settings')
  await expect(page).toHaveURL(/\/results$/)
  await expect(page.getByRole('link',{name:'Настройки',exact:true})).toHaveCount(0)
  await page.getByRole('link',{name:'Открыть',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Готовый отчёт'})).toBeVisible()
  await expect(page.getByRole('button',{name:/Скачать всю сортировку/})).toBeEnabled()
  await expect(page.getByRole('button',{name:'Удалить всю партию'})).toHaveCount(0)
  expect(unexpected).toEqual([])
})

test('owner creates a viewer directly and can revoke its selected reports',async({page})=>{
  await page.route('**/api/auth/me',route=>route.fulfill({json:{username:'admin'}}))
  await page.route('**/api/admin/access-requests?**',route=>route.fulfill({json:{items:[],has_more:false}}))
  const report={id:run,display_name:'Готовый отчёт',status:'completed'}
  await page.route('**/api/results/catalog?**',route=>route.fulfill({json:{items:[report],has_more:false}}))
  const user={id:2,email,created_at:'2026-11-15T12:00:00Z'}
  let created=false,grants=[report]
  await page.route(/\/api\/admin\/users(?:\?.*)?$/,route=>{
    if(route.request().method()==='POST'){
      expect(route.request().postDataJSON()).toEqual({email,password,confirmation:password,run_ids:[run]})
      created=true
      return route.fulfill({status:201,json:user})
    }
    return route.fulfill({json:{items:created?[user]:[],has_more:false}})
  })
  await page.route('**/api/admin/users/2/grants',route=>{
    if(route.request().method()==='PUT'){
      expect(route.request().postDataJSON()).toEqual({run_ids:[]})
      grants=[]
    }
    return route.fulfill({json:{items:grants}})
  })
  await page.goto('/admin')
  await page.getByRole('button',{name:'Создать пользователя'}).click()
  const create=page.getByRole('dialog',{name:'Создать пользователя'})
  await create.getByLabel('Электронная почта').fill(email)
  await create.getByLabel('Начальный пароль').fill(password)
  await create.getByLabel('Повторите пароль').fill(password+'-typo')
  await create.getByRole('checkbox',{name:/Готовый отчёт/}).check()
  await create.getByRole('button',{name:'Создать',exact:true}).click()
  await expect(create.getByRole('alert')).toHaveText('Пароли не совпадают.')
  expect(created).toBe(false)
  await create.getByLabel('Повторите пароль').fill(password)
  await create.getByRole('button',{name:'Создать',exact:true}).click()
  await expect(create).toHaveCount(0)
  const accounts=page.getByRole('region',{name:'Аккаунты'})
  await expect(accounts.getByText(email,{exact:true})).toBeVisible()
  await accounts.getByRole('button',{name:'Изменить доступ'}).click()
  const edit=page.getByRole('dialog',{name:'Выдать доступ к результатам'})
  const option=edit.getByRole('checkbox',{name:/Готовый отчёт/})
  await expect(option).toBeChecked()
  await option.uncheck()
  await edit.getByRole('button',{name:'Сохранить'}).click()
  await expect(edit).toHaveCount(0)
})
