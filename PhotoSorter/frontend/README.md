# OUTDOOR PhotoSorter — единый интерфейс Vue 3

**Один сайт:** HTTPS `/` обслуживает Vue SPA; маршруты `/fo`, `/references`, `/processing`, `/results`, `/logs`, `/settings`, `/login` работают без версии в адресе. Старый HTML/JS/CSS удалён, `/v3/` и `/static/app.js` недоступны.

## Разработка и тесты

```bash
npm ci
npm run dev
npm run build
npm run test
npx playwright install chromium webkit
npm run test:e2e
```

Node 24. Dev Vite слушает `http://127.0.0.1:5173/` с прокси `/api` на изолированный backend. Не направляйте dev proxy на рабочий VPS. В production Caddy проксирует запросы в один FastAPI, который отдаёт готовые Vue assets и API на том же домене.

- `src/app`: auth gate и history router; `src/stores`: session/theme/toasts.
- `src/api`: типизированный клиент; `src/types`: контракты API.
- `src/features`: отдельные разделы PhotoSorter; `src/components`: переиспользуемый UI.
- `src/components/gallery/VirtualThumbnailGrid.vue`: только видимые карточки.
- `src/styles`: общая тема и адаптивная сетка.
- `tests`: Vitest; `e2e`: Playwright Chromium/WebKit desktop/mobile.

Фото, модель MegaLoc, каталог `Models` и базы PostgreSQL не являются частью frontend bundle. Полная карта: [../../../PROJECT_MAP.md](../../../PROJECT_MAP.md).

## Единый визуальный стиль

Нейтральная монохромная тема без декоративных стрелок и системных меню выбора:
- `src/styles/tokens.css` — только палитры `dark` / `light` и базовые токены.
- `src/styles/base.css` — общие правила типографики и полей.
- `src/styles/components.css` — единственные актуальные стили панелей, кнопок, навигации, галерей и адаптивной компоновки.
- `src/styles/select.css` — оформление единственного кастомного `UiSelect`.
- `src/components/ui/UiSelect.vue` — доступный select-only combobox, без стрелок, с клавиатурой и закрытием вне поля.
- `src/components/ui/UiIcon.vue` — единые SVG-иконки навигации без дополнительных npm-зависимостей.

Элементы, принадлежащие одной feature, остаются внутри `src/features/<feature>/`. API, обработка MegaLoc, данные и маршруты не затрагиваются визуальной темой. Для браузерных меню не использовать нативный `<select>` без специального обоснования. Запрещено копировать из Uiverse разнородные CSS без приведения к общим токенам.
