import { createRouter, createWebHistory } from 'vue-router'
export const router = createRouter({
  history: createWebHistory('/'),
  scrollBehavior(to, from, saved) { return saved ?? (to.path !== from.path ? { top: 0 } : undefined) },
  routes: [
    { path: '/', redirect: '/fo' },
    { path: '/login', name: 'login', component: () => import('../features/auth/LoginView.vue'), meta: { public: true } },
    { path: '/fo', name: 'fo', component: () => import('../features/fo/FoList.vue') },
    { path: '/fo/:batchId', name: 'fo-gallery', component: () => import('../features/fo/FoGallery.vue') },
    { path: '/references', name: 'references', component: () => import('../features/references/ReferenceLibrary.vue') },
    { path: '/layouts', name: 'layouts', component: () => import('../features/layouts/AdLayoutLibrary.vue') },
    { path: '/queue', name: 'queue', component: () => import('../features/queue/QueueView.vue') },
    { path: '/queue/runs/:runId', name: 'run-detail', component: () => import('../features/queue/RunDetail.vue') },
    { path: '/results', name: 'results', component: () => import('../features/results/ResultsList.vue') },
    { path: '/results/:runId', name: 'result-detail', component: () => import('../features/results/ResultDetail.vue') },
    { path: '/logs', name: 'logs', component: () => import('../features/logs/LogsView.vue') },
    { path: '/settings', name: 'settings', component: () => import('../features/settings/SettingsView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/fo' }
  ]
})
