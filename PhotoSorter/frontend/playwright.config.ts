import {defineConfig,devices} from '@playwright/test'
export default defineConfig({
  testDir:'./e2e',fullyParallel:true,forbidOnly:!!process.env.CI,
  retries:process.env.CI?1:0,workers:process.env.CI?2:undefined,
  reporter:process.env.CI?[['list'],['html',{open:'never'}]]:'list',
  use:{baseURL:'http://127.0.0.1:5173/v3/',trace:'retain-on-failure',screenshot:'only-on-failure'},
  projects:[
    {name:'chromium-desktop',use:{...devices['Desktop Chrome']}},
    {name:'webkit-desktop',use:{...devices['Desktop Safari']}},
    {name:'webkit-mobile',use:{...devices['iPhone 13']}}
  ],
  webServer:{
    command:'npm run dev -- --host 127.0.0.1',
    url:'http://127.0.0.1:5173/v3/',
    reuseExistingServer:!process.env.CI,
    timeout:120000
  }
})
