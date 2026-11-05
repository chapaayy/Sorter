# Дизайн-система OUTDOOR PhotoSorter — этап 3 (Vue 3)

**Реализовано в stage3 branch** в `PhotoSorter/frontend/src/styles/` и `components/`. Не развёрнуто на работающем VPS; прежний UI продолжает работать на `/`, новый — `/v3/` после сборки Docker.

- Тёмная графитовая тема: `--page:#0d1110`, `--sidebar:#101513`, `--panel:#171d19`, `--accent:#91c47e`; светлая: `--page:#f6f7f5`, `--panel:#fff`, `--accent:#4f8652`. Единая палитра CSS tokens для кнопок, модалок, инпутов, таблиц, подсказок.
- Переключение `system/dark/light` с реакцией на `prefers-color-scheme`; предпочтение хранится под `ps.theme.v3` (не cookie).
- Шесть разделов: **ФО / Образцы / Обработка / Результаты / Логи / Настройки**. Отдельной «Главной» нет.
- `RowCard`: фиксированная высота **108 px**, статус/mini-preview/проценты не меняют высоту. Карточки кликабельные, с темой и focus-visible.
- ФО: список партий `/fo`; отдельная галерея `/fo/:batchId`; фото только thumbnails, оригинал по клику, delete only before first run.
- Образцы: desktop SAM слева, фотографии справа; mobile selector над фотосеткой. Библиотека общая, не привязана к партии.
- Результаты: список запусков → два режима SAM/группы; `_Неопределено` как «Неопределено» и в конце списка, не теряется. Основная кнопка полного ZIP отдельно от его подтверждения; двухмесячный retention и warning/extend.
- Viewer: полноразмерное изображение, стрелки клавиатуры, Escape, свайп, dblclick масштаб, overlay, focus.
- Основные кнопки и mobile drawer имеют targets ≈42–46px; требуется отдельная ручная проверка на iPhone/Safari и увеличение до 44px, если Lighthouse/ручная проверка выявит недостаток.
- Прогресс: только действительные stage current/total/ETA и измеренный per-second; неизвестные значения `—`, не генерировать fake overall/score.
- Общие элементы: `UiButton`, `PageHeader`, `RowCard`, `GroupPicker`, `ThumbnailGrid`, `ImageViewer`, `ConfirmDialog`, `ToastStack`.
- Keyboard focus, aria-live notifications and aria-modal for confirmation; reduced motion @media.

Browser functional tests выполняются на mock API в GitHub Actions. Визуальная QA на реальном Safari и реальных 1315 фото относится к отдельной приёмке, **не утверждается как выполненная автоматически**.

## Виртуализация больших галерей

`VirtualThumbnailGrid.vue` вычисляет количество колонок по ширине, выбирает видимые строки с запасом и рендерит внутри `ThumbnailGrid` только их. При мобильной ширине адаптирует колонны до двух, отслеживает scroll/resize и сохраняет реальный индекс при открытии full-size viewer. Курсовая подгрузка сохраняется отдельной composable `useCursor`, так что память UI не включает весь 1315+ dataset в одном API ответе. Нет скрытого скачивания полноразмерных файлов на каждую карточку.
