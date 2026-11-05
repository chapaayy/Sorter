# FILE_INDEX.md — актуальные файлы PhotoSorter (ветка main)

Индекс только существующих и используемых модулей. Не включает пустые `__init__.py`, `.gitkeep`, запакованные зависимости и собранный Vue `dist/`. Каждая правка структуры должна обновлять этот файл.

## Корень и инфраструктура

| Файл / каталог | Назначение |
|---|---|
| `README.md` | Главная инструкция бета-версии, запуск, каталоги данных |
| `AGENTS.md` | Правила разработки, безопасность, запрет изменения MegaLoc |
| `PROJECT_MAP.md` | Архитектура, потоки данных, зависимости слоёв |
| `FILE_INDEX.md` | Индекс обязанностей файлов |
| `install.sh` | Установка/обновление, preflight, сохранение действующих паролей и mounts |
| `compose.yaml` | Caddy, PostgreSQL, API, MegaLoc Worker, WebP и cleanup |
| `.env.example` | Шаблон DOMAIN, не содержит реальные секреты |
| `.dockerignore`, `.gitignore` | Исключение секретов, ФО, моделей, caches, build artifacts |
| `.github/workflows/ci.yml` | **Единственный** актуальный CI (backend, restore, frontend, browser, full Docker runtime) |
| `PhotoSorter/docker/app/Dockerfile` | Node 24 Vue build stage + Python/CPU PyTorch runtime |
| `PhotoSorter/docker/caddy/Caddyfile` | HTTPS reverse proxy, лимиты запросов и security headers |

## Backend / API

| Файл / каталог | Назначение |
|---|---|
| `backend/server/main.py` | FastAPI assembly, auth middleware, lifespan, health |
| `backend/server/auth.py` | Cookies, scrypt password, login, origin checks |
| `backend/server/database.py` | PostgreSQL connect, initial schema and migrations |
| `backend/server/uploads.py` | Resumable upload, финализация, проверки оригиналов |
| `backend/server/jobs.py` | Создание/отмена заданий, API очереди |
| `backend/server/worker.py` | Однопоточный lifecycle MegaLoc Worker и heartbeat |
| `backend/server/reference_cache.py` | Индекс и доступ к embeddings образцов |
| `backend/server/api/routes/site.py` | **Один** Vue сайт на `/`, `/assets/*` и history fallback |
| `backend/server/api/routes/auth.py` | Login/logout/current user endpoints |
| `backend/server/api/routes/batches.py` | Партии, метаданные и безопасное удаление |
| `backend/server/api/routes/references.py` | Галерея, проверка пакета, адрес конструкции и удаление образцов |
| `backend/server/api/routes/models.py` | Модели, скачивание и состояние |
| `backend/server/api/routes/results.py` | История прогонов и результаты |
| `backend/server/api/routes/images.py` | Изображения результатов |
| `backend/server/api/routes/originals.py` | Оригиналы через operation lease |
| `backend/server/api/routes/thumbnails.py` | WebP превью и queue state |
| `backend/server/api/routes/downloads.py` | Streaming ZIP, подтверждения, пути внутри ZIP |
| `backend/server/api/routes/logs.py` | Cursor/log tail, скачивание |
| `backend/server/api/routes/storage.py` | Статистика физического места |
| `backend/server/api/routes/system.py` | Worker heartbeat, system health и служебная очистка |

## Backend / services, storage, DB

| Файл / каталог | Назначение |
|---|---|
| `backend/server/services/batches.py` | Состояния и CRUD партий |
| `backend/server/services/references.py` | Безопасное редактирование и удаление конструкций, защита исторических manifests |
| `backend/server/services/construction_catalog.py` | Серверная проверка массового импорта, метаданные и адреса конструкций |
| `backend/server/services/retention.py` | Подтверждение ZIP, срок хранения, предупреждения |
| `backend/server/services/cleanup.py` | Удаление только owned files через доверенные UUID |
| `backend/server/services/temp_cleanup.py` | Устаревшие незавершённые передачи |
| `backend/server/services/thumbnails.py` | WebP queue и кеширование превью |
| `backend/server/services/thumbnail_gc.py` | Сборка вызовов очистки WebP cache |
| `backend/server/services/result_pages.py` | Галереи/пагинация снимков результата |
| `backend/server/services/storage_usage.py` | Диск, категории, учёт inode/Hard Link |
| `backend/server/services/disk_guard.py` | Дисковый reserve и HTTP 507 для новых uploads |
| `backend/server/services/operations.py` | Долгоживущие операции/leases |
| `backend/server/services/heartbeat.py` | Пульс процессов worker/thumbnail/cleanup |
| `backend/server/security/login_throttle.py` | Ограничение неверных логинов |
| `backend/server/db/migration_runner.py` | Пошаговая миграция PostgreSQL |
| `backend/server/db/migrations/0001…0008*.sql` | **Аддитивная история схемы БД**, включая каталог конструкций |
| `backend/server/db/repositories/batches.py` | SQL для партий |
| `backend/server/db/repositories/queue.py` | Очередь MegaLoc и лидер |
| `backend/server/db/repositories/pagination.py` | Cursor pagination для галерей |
| `backend/server/storage/paths.py` | Проверенные доверенные пути |
| `backend/server/storage/hardlinks.py` | Hard Link с безопасным fallback |
| `backend/server/storage/thumbnail_cache.py` | Дисковый WebP cache |
| `backend/server/workers/thumbnail.py` | Цикл генерации WebP |
| `backend/server/workers/cleanup.py` | Фоновый retention и trash cleanup |

## MegaLoc и фотологика

| Файл / каталог | Назначение |
|---|---|
| `backend/app/recognition/pipeline.py` | Порядок ФО → группировка → назначение SAM |
| `backend/app/recognition/engines/base.py` | Интерфейс inference |
| `backend/app/recognition/engines/megaloc/extractor.py` | Получение признаков MegaLoc |
| `backend/app/recognition/engines/megaloc/loader.py` | Загрузка модели/весов |
| `backend/app/recognition/grouping/finder.py` | Группы ФО |
| `backend/app/recognition/matching/resolver.py` | Подбор SAM |
| `backend/app/recognition/math.py`, `errors.py` | Численные операции/ошибки |
| `backend/app/jobs/{worker,runtime,progress,overall_progress}.py` | Стадии исполнения, прогресс |
| `backend/app/results/{copier,exporter,repository}.py` | Manifest, публикация файлов и результат |
| `backend/app/logging/events.py` | JSONL события, ротация |
| `backend/app/photos/{labels,reader,scanner}.py` | Сканирование/старые метки/чтение изображений |
| `backend/app/photos/construction.py` | Строгий формат `CITY NUMBER — ADDRESS`, коды городов |
| `backend/app/system/{downloads,model_store,performance}.py` | Загрузка/проверка моделей, ресурсные функции |
| `backend/app/config.py` | Пути и гарантированная структура каталогов |

## Единственный фронтенд Vue 3

| Файл / каталог | Назначение |
|---|---|
| `frontend/package.json`, `package-lock.json` | Бета-версия, зафиксированные зависимости, scripts |
| `frontend/index.html`, `vite.config.ts`, `tsconfig.json` | Bootstrap HTML, Vite base `/`, TS проверки |
| `frontend/src/main.ts` | Подключение Vue, Pinia, Router, CSS |
| `frontend/src/app/App.vue`, `router.ts` | Session gate и чистые маршруты |
| `frontend/src/api/{client,batches,references,runs,results,logs,system}.ts` | Типизированный слой HTTP |
| `frontend/src/types/api.ts` | Контракты JSON |
| `frontend/src/stores/{session,theme,notice}.ts` | Вход, тема, уведомления |
| `frontend/src/composables/{useCursor,usePolling}.ts` | Cursor/polling, предотвращение дублирующихся запросов |
| `frontend/src/composables/useReferenceTransfer.ts` | Общая докачка и параллельная передача образцов |
| `frontend/src/components/layout/Shell.vue` | Шесть вкладок, mobile menu |
| `frontend/src/components/ui/` | Buttons, confirmation, empty state, toast, карточки |
| `frontend/src/components/gallery/` | Lazy/virtual thumbnails и ImageViewer |
| `frontend/src/components/split/GroupPicker.vue` | Двухпанельный выбор и мобильная версия |
| `frontend/src/features/auth/LoginView.vue` | Логин |
| `frontend/src/features/fo/` | Список ФО, галерея, загрузка |
| `frontend/src/features/references/ReferenceLibrary.vue` | Библиотека с городом, номером, адресом и просмотром фото |
| `frontend/src/features/references/ReferenceUploader.vue` | Переключение двух способов импорта |
| `frontend/src/features/references/ReferenceDirectoryImporter.vue` | Строгий массовый импорт, предпросмотр и ошибки по каждому файлу |
| `frontend/src/features/references/ReferencePhotoUploader.vue` | Добавление фотографий в выбранную конструкцию |
| `frontend/src/features/processing/` | Очередь MegaLoc, обработка, детализация |
| `frontend/src/features/results/` | Результаты, ZIP, сохранение/retention |
| `frontend/src/features/logs/LogsView.vue` | Лог обработки, tail |
| `frontend/src/features/settings/SettingsView.vue` | Диск, состояние сервисов, тема, cleanup |
| `frontend/src/styles/` | CSS tokens, layout, components |
| `frontend/src/utils/{upload,format}.ts` | Resumable upload, форматы |
| `frontend/src/utils/referenceSelection.ts` | Клиентская проверка имени папки, учёт всех выбранных файлов |
| `frontend/src/utils/uploadQueue.ts` | Ограничение и отчёт ошибок параллельных передач |
| `frontend/src/stores/uploadSettings.ts` | Настройка числа одновременных загрузок |
| `frontend/src/utils/batches.ts` | Общие проверки готовности ФО к обработке и безопасного возобновления загрузки |

## Проверки и обслуживание

| Файл | Назначение |
|---|---|
| `backend/tests/` | Backend regression: SQL, MegaLoc math, безопасность, upload, ZIP, retention и HTTP |
| `backend/tests/test_batch_listing_regressions.py` | Счётчики нулевых запусков, список ФО после удаления, PostgreSQL |
| `backend/tests/test_construction_import.py` | Новый формат конструкций, повторные импорты, SHA-256, адреса |
| `frontend/tests/` | Vitest |
| `frontend/e2e/navigation.spec.ts`, `playwright.config.ts` | Chromium/WebKit на десктопе и mobile |
| `PhotoSorter/tools/benchmark_api.py` | API latency |
| `PhotoSorter/tools/maintenance/snapshot.py` | Согласованный backup, verify, disposable restore-test |
| `PhotoSorter/tools/maintenance/ci_restore_drill.py` | CI dump→restore на изолированной PostgreSQL |
| `PhotoSorter/tools/maintenance/compare_baseline.py` | Две реальных MegaLoc manifest/ZIP для сравнения |
| `PhotoSorter/tools/maintenance/staging_probe.py` | Read-only health, latency, resources |
| `PhotoSorter/tools/maintenance/smoke_container.sh` | Только одноразовый CI Docker runtime |
| `docs/` | Актуальные API, архитектура, backup, deployment, operations, security, acceptance и rollback |

См. [Инструкция импорта образцов](docs/REFERENCE_IMPORT.md).

**Что не входит в актуальный код:** `frontend/static`, маршрут `/v3`, отдельные старые stage CI и второй JS/HTML-фронтенд. Исторические имена `test_stage*.py` остаются регрессионными тестами, а рабочие инструменты находятся в `tools/maintenance/` — параллельных версий приложения нет.

### UI: единый монохромный слой (dark/light)
- `PhotoSorter/frontend/src/components/ui/UiSelect.vue` — единый доступный раскрывающийся список без стрелок и нативного меню.
- `PhotoSorter/frontend/src/components/ui/UiIcon.vue` — SVG-навигация без внешнего icon runtime.
- `PhotoSorter/frontend/src/styles/tokens.css` — цветовые токены тёмной/светлой темы.
- `PhotoSorter/frontend/src/styles/components.css` — единое актуальное оформление и адаптивная компоновка без каскадных тем-надстроек.
- `PhotoSorter/frontend/src/styles/select.css` — стили кастомного выпадающего меню.
- `PhotoSorter/frontend/e2e/navigation.spec.ts` — браузерная проверка выбора партии, Esc и существующей навигации.
