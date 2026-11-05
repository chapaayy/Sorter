import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './app/App.vue'
import { router } from './app/router'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'
import './styles/select.css'
createApp(App).use(createPinia()).use(router).mount('#app')
