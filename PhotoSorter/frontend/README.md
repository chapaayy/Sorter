# OUTDOOR PhotoSorter · Vue 3 UI — Stage 3

Новый UI обслуживается по `/v3/`; **legacy UI остаётся на `/`**, пока не проведена приёмка. Не направляйте Vite proxy на рабочий VPS и не загружайте реальные ФО в тестовый стенд без разрешения.

## Установка и проверки

```bash
npm ci
npm run dev
npm run typecheck
npm run build
npm run test
npx playwright install chromium webkit
npm run test:e2e
```

Node 24, точный `package-lock.json`. Для настоящих POST с cookie/Origin на dev требуется backend test environment и корректная конфигурация origin; Playwright тесты вместо этого используют mock API, production обслуживается тем же доменом, что и backend.

## Назначение модулей

- `src/app`: auth gate/router; `src/stores`: session/theme/toasts.
- `src/api`: все сетевые вызовы; `src/types`: контракты backend, `src/composables`: polling и cursor pagination.
- `src/features`: каждая вкладка собственными Vue SFC; `src/components`: единые визуальные элементы.
- `src/components/gallery/VirtualThumbnailGrid.vue`: не держит 1315 карточек в DOM; `ImageViewer.vue`: полный оригинал только по клику.
- `src/styles`: graphite/light/system tokens and mobile responsive layout.
- `tests`: Vitest, `e2e`: Playwright Chromium/WebKit desktop/mobile с тестовыми API ответами.

Рабочие данные PhotoSorter, MegaLoc math/weights, Caddy HTTPS и старая страница не менялись. Полная карта проекта: [../../../PROJECT_MAP.md](../../../PROJECT_MAP.md).
