import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './app/App.vue'
import { router } from './app/router'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'
import './styles/select.css'
import './styles/task-cards.css'
import './styles/upload-dialog.css'
import './styles/reference-layout.css'
import './styles/reference-sides.css'
import './styles/settings-layout.css'
import './styles/skeleton.css'
const app=createApp(App).use(createPinia()).use(router)
// Resolve the initial lazy route before App restores the session. Otherwise
// a fast unauthenticated response can redirect from the START_LOCATION '/'
// and discard the actual requested deep link.
void router.isReady().then(()=>app.mount('#app'))
