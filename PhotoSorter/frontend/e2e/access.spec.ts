import {test,expect} from '@playwright/test'

const email='viewer@example.test', password='example-only-passphrase'
const run='20261114T170000-0123456789ab'
const item={id:'00000000-0000-4000-8000-000000000001',email,comment:'Я из отдела рекламы. Нужны готовые фотоотчёты.',
  status:'pending',created_at:'2026-11-14T17:00:00Z',decided_at:null}

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
  await page.getByRole('button',{name:/Пользователи/}).click()
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
