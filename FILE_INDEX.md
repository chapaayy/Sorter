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
| `backend/server/uploads.py` | Докачка, проверка принадлежности манифесту, финализация с сохранением `.part` до commit и выборочная отмена |
| `backend/server/jobs.py` | Единое транзакционное создание заданий, API очереди и остановки, проверка состояния ZIP и ZIP-only retry |
| `backend/server/worker.py` | Однопоточный lifecycle MegaLoc Worker и heartbeat |
| `backend/server/reference_cache.py` | Индекс и доступ к embeddings образцов |
| `backend/server/api/routes/site.py` | **Один** Vue сайт на `/`, `/assets/*` и history fallback |
| `backend/server/api/routes/auth.py` | Login/logout/current user endpoints |
| `backend/server/api/routes/batches.py` | Партии, серверный манифест, отмена ожидаемой автообработки, незавершённые загрузки и безопасное удаление |
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
| `backend/server/api/routes/processing_settings.py` | Общие PostgreSQL-настройки автообработки и порога: GET/PATCH |

## Backend / services, storage, DB

| Файл / каталог | Назначение |
|---|---|
| `backend/server/services/batches.py` | CRUD партий, счётчики, последний запуск MegaLoc/прошлый результат для списка ФО, pending uploads |
| `backend/server/services/upload_manifest.py` | Неизменяемый состав новой партии, индивидуальная настройка auto-MegaLoc, проверка оригиналов и завершение `waiting/complete` |
| `backend/server/services/batch_runs.py` | Безопасные сводки запусков, реальные счётчики MegaLoc для компактных карточек и история без путей ФС |
| `backend/server/services/auto_processing.py` | Защищённая отмена, общие настройки, серверная постановка opt-in партий через общую очередь (idempotent DB lock) |
| `backend/server/services/references.py` | Безопасное редактирование и удаление конструкций, защита исторических manifests |
| `backend/server/services/construction_catalog.py` | Серверная проверка массового импорта, метаданные и адреса конструкций |
| `backend/server/services/archive_pipeline.py` | Обязательный финальный ZIP после результатов MegaLoc; обновляет прогресс этапа |
| `backend/server/services/archives.py` | Атомарный ZIP_STORED, проверка CRC перед публикацией, повторное использование готового архива |
| `backend/server/services/archive_retries.py` | Сохранённая в PostgreSQL очередь ZIP-only восстановления и обнаружение пропавшего архива |
| `backend/server/services/retention.py` | Срок хранения от успешного ZIP, глобальная пауза при выключении и безопасный повторный запуск политики |
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
| `backend/server/db/migrations/0001…0010*.sql` | **Аддитивная история схемы БД**, включая манифест ФО и настройки opt-in автообработки |
| `backend/server/db/repositories/batches.py` | SQL для партий, совместимые с манифестом правила `upload_state` |
| `backend/server/db/repositories/pagination.py` | Cursor pagination для галерей |
| `backend/server/storage/paths.py` | Проверенные доверенные пути |
| `backend/server/storage/hardlinks.py` | Hard Link с безопасным fallback |
| `backend/server/storage/thumbnail_cache.py` | Дисковый WebP cache |
| `backend/server/workers/thumbnail.py` | Цикл генерации WebP |
| `backend/server/workers/cleanup.py` | Фоновая постановка готовых opt-in партий в MegaLoc FIFO, retention и trash cleanup |

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
| `frontend/src/components/layout/Shell.vue` | Шесть вкладок; сворачиваемая desktop-панель и mobile drawer |
| `frontend/src/components/ui/` | Buttons, confirmation, empty state, toast, карточки |
| `frontend/src/components/gallery/` | Lazy/virtual thumbnails и ImageViewer |
| `frontend/src/components/split/GroupPicker.vue` | Двухпанельный выбор: однострочные подписи, счётчики, tooltip, регулируемая ширина с сохранением в браузере; мобильная версия |
| `frontend/src/features/auth/LoginView.vue` | Логин |
| `frontend/src/features/fo/` | Список и галерея ФО, загрузка, восстановление и встроенные состояния MegaLoc |
| `frontend/src/features/fo/FoBatchCard.vue` | Компактная карточка партии, ссылки и доступные действия MegaLoc |
| `frontend/src/features/fo/BatchProcessingStatus.vue` | Общий блок статуса/реального прогресса MegaLoc в списке и галерее |
| `frontend/src/features/fo/BatchRunHistory.vue` | Постраничная история всех запусков партии, включая предыдущие результаты |
| `frontend/src/utils/batchProcessing.ts` | Правила UI-состояний MegaLoc, отдельные от состояния миниатюр |
| `frontend/src/features/fo/PendingUploads.vue` | Докачка по выбранному оригиналу, автозавершение полностью принятых файлов, подтверждаемая отмена |
| `frontend/src/features/references/ReferenceLibrary.vue` | Библиотека с городом, номером, адресом и просмотром фото |
| `frontend/src/features/references/ReferenceUploader.vue` | Переключение двух способов импорта |
| `frontend/src/features/references/ReferenceDirectoryImporter.vue` | Строгий массовый импорт, предпросмотр, ошибки и видимый список системных файлов, исключённых из передачи |
| `frontend/src/features/references/ReferencePhotoUploader.vue` | Добавление фотографий в выбранную конструкцию |
| `frontend/src/features/results/` | Результаты, ZIP, сохранение/retention |
| `frontend/src/features/logs/LogsView.vue` | Лог обработки, tail |
| `frontend/src/features/settings/SettingsView.vue` | Диск, состояние сервисов, тема, cleanup |
| `frontend/src/styles/` | CSS tokens, единственный общий UI-слой; адаптивные стили списка и свёрнутого меню |
| `frontend/src/utils/{upload,format}.ts` | Idempotent resume, блоки 16 МиБ, безопасная проверка файла, форматы |
| `frontend/src/utils/uploadRetry.ts` | Отменяемые повторные запросы/backoff при переключении VPN или потере сети |
| `frontend/src/utils/referenceSelection.ts` | Клиентская проверка имени папки, полный учёт фото/ошибок/явно пропущенных системных файлов ОС |
| `frontend/src/utils/referenceDuplicates.ts` | SHA-256 сверка с готовыми образцами перед сетевой загрузкой |
| `frontend/src/utils/uploadQueue.ts` | Ограничение и отчёт ошибок параллельных передач |
| `frontend/src/stores/uploadSettings.ts` | Настройка числа одновременных загрузок |
| `frontend/src/stores/sidebar.ts` | Сохранение состояния свёрнутого desktop-меню в localStorage |
| `frontend/src/utils/batches.ts` | Общие проверки готовности ФО к обработке и безопасного возобновления загрузки |

## Проверки и обслуживание

| Файл | Назначение |
|---|---|
| `backend/tests/` | Backend regression: SQL, MegaLoc math, безопасность, upload, ZIP, retention и HTTP |
| `backend/tests/test_batch_listing_regressions.py` | Счётчики нулевых запусков, список ФО после удаления, PostgreSQL |
| `backend/tests/test_construction_import.py` | Новый формат конструкций, повторные импорты, SHA-256, адреса |
| `backend/tests/test_pending_upload_recovery.py` | Изолированные проверки автозавершения `.part`, idempotent init и отмены без потери готовых фото |
| `backend/tests/test_processing_dashboard.py` | Новый фильтр запусков, статус PostgreSQL, пагинация, совместимость прежнего API |
| `backend/tests/test_batch_run_summaries.py` | Действительный latest run, позиция очереди, прогресс, прежний результат и безопасная история |
| `backend/tests/test_auto_processing.py` | Новая opt-in очередь, отмена до enqueue, ручной запуск, queue full, terminal job, конкурентная отправка, старые партии |
| `backend/tests/test_archive_recovery.py` | Восстановление пропавшего ZIP без MegaLoc, запрет публикации архива с ошибкой CRC |
| `backend/tests/test_retention_toggle.py` | Приостановка автоудаления и безопасный новый срок после повторного включения |
| `backend/tests/test_batch_card_metadata.py` | Реальные группы/неопределённые ФО в карточках без утечки приватных путей |
| `frontend/tests/` | Vitest |
| `frontend/e2e/navigation.spec.ts`, `playwright.config.ts` | Chromium/WebKit на десктопе и mobile |
| `PhotoSorter/tools/benchmark_api.py` | API latency |
| `PhotoSorter/tools/maintenance/snapshot.py` | Согласованный backup, verify, disposable restore-test |
| `PhotoSorter/tools/maintenance/ci_restore_drill.py` | CI dump→restore на изолированной PostgreSQL |
| `PhotoSorter/tools/maintenance/compare_baseline.py` | Две реальных MegaLoc manifest/ZIP для сравнения |
| `PhotoSorter/tools/maintenance/staging_probe.py` | Read-only health, latency, resources |
| `PhotoSorter/tools/maintenance/smoke_container.sh` | Только одноразовый CI Docker runtime |
| `docs/STAGE4_ACCEPTANCE.md` | Итоговая проверка: автоматизированные сценарии и отдельно обязательные ручные тесты VPN/Worker/VPS |
| `docs/` | Актуальные API, архитектура, backup, deployment, operations, security, acceptance и rollback |

См. [Инструкция импорта образцов](docs/REFERENCE_IMPORT.md).

**Что не входит в актуальный код:** `frontend/static`, маршрут `/v3`, отдельные старые stage CI и второй JS/HTML-фронтенд. Исторические имена `test_stage*.py` остаются регрессионными тестами, а рабочие инструменты находятся в `tools/maintenance/` — параллельных версий приложения нет.

### UI: единый монохромный слой (dark/light)
- `PhotoSorter/frontend/src/components/ui/UiSelect.vue` — единый доступный раскрывающийся список с маленьким CSS-chevron и нативного меню.
- `PhotoSorter/frontend/src/components/ui/UiIcon.vue` — SVG-навигация без внешнего icon runtime.
- `PhotoSorter/frontend/src/styles/tokens.css` — цветовые токены тёмной/светлой темы.
- `PhotoSorter/frontend/src/styles/components.css` — единое актуальное оформление и адаптивная компоновка без каскадных тем-надстроек.
- `PhotoSorter/frontend/src/styles/select.css` — стили кастомного выпадающего меню.
- `PhotoSorter/frontend/e2e/navigation.spec.ts` — браузерная проверка выбора партии, Esc и существующей навигации.


## Единственный reference/FIFO pipeline

| Файл | Ответственность |
|---|---|
| `PhotoSorter/backend/server/db/repositories/work_queue.py` | FIFO `seq`, claim, остановка/сбой/возобновление |
| `PhotoSorter/backend/server/db/repositories/job_status.py` | Только публичные статусы и позиции ФО |
| `PhotoSorter/backend/server/db/repositories/reference_imports.py` | SQL сессии, файлы, prep job |
| `PhotoSorter/backend/server/db/repositories/reference_versions.py` | Чтение опубликованного снимка |
| `PhotoSorter/backend/server/services/reference_imports.py` | Полный манифест, финализация сессии |
| `PhotoSorter/backend/server/services/reference_uploads.py` | SHA-256, чанки, дедупликация |
| `PhotoSorter/backend/server/services/reference_publication.py` | V1/новые неизменяемые версии, атомарная публикация |
| `PhotoSorter/backend/server/services/reference_gallery.py` | Галерея как производное от готовых файлов |
| `PhotoSorter/backend/server/services/references.py` | Удаление из опубликованной версии и кэш-статус |
| `PhotoSorter/backend/server/services/upload_validation.py` | Общая валидация имени и размера фото |
| `PhotoSorter/backend/server/workers/reference_prepare.py` | CPU-подготовка MegaLoc, публикация и прогресс |
| `PhotoSorter/backend/server/storage/reference_objects.py` | Изолированное файловое staging-хранилище |
| `PhotoSorter/backend/server/api/routes/reference_imports.py` | API сессий, файлов, статуса и возобновления |
| `PhotoSorter/backend/server/api/routes/references.py` | Каталог/галерея/удаление |
| `PhotoSorter/frontend/src/composables/useReferenceTransfer.ts` | Единственный resumable загрузчик образцов |
| `PhotoSorter/frontend/src/types/referenceTransfer.ts` | Тип выбранного образца |
| `PhotoSorter/frontend/src/features/queue/*` | Общая очередь |
| `PhotoSorter/frontend/src/features/references/*` | Загрузка, статус подготовки, библиотека |
| `PhotoSorter/frontend/src/features/fo/ReferenceUpdateNotice.vue` | Однократное предупреждение |

SQL-изменения до `0016_library_notice_delivery.sql` сохраняются
как последовательные миграции **схемы**, но не содержат альтернативных
обработчиков/версий приложения. Более подробная текущая схема в
`docs/REFERENCE_PIPELINE.md`.


## Компоненты единого компактного списка

| Файл | Задача |
|---|---|
| `PhotoSorter/frontend/src/components/ui/CompactTaskCard.vue` | Одна горизонтальная карточка ФО/очереди/результатов: фото, статус, прогресс, время, действия |
| `PhotoSorter/frontend/src/styles/task-cards.css` | Адаптивные светлые/тёмные стили карточек, нейтральные цвета обеих тем |
| `PhotoSorter/frontend/src/utils/queueEstimates.ts` | ETA FIFO из реальных измерений: отдельные скорости ФО и подготовки образцов |
| `PhotoSorter/frontend/tests/queueEstimates.test.ts` | Очерёдность, отсутствие неподтверждённых ETA, фактическая длительность |


## Модульное обновление интерфейса

| Путь | Задача |
|---|---|
| `PhotoSorter/frontend/src/components/upload/UploadCenter.vue` | Единый глобальный диалог ФО / образцов |
| `PhotoSorter/frontend/src/stores/uploadCenter.ts` | Состояние видимости, текущая загрузка |
| `PhotoSorter/frontend/src/styles/upload-dialog.css` | Модалка и фоновый индикатор |
| `PhotoSorter/frontend/src/styles/reference-layout.css` | Два независимых scroll-контейнера образцов |
| `PhotoSorter/frontend/src/styles/queue.css` | Пустое состояние очереди |
| `PhotoSorter/frontend/src/styles/settings-layout.css` | Навигация категорий настроек |
| `PhotoSorter/frontend/src/features/queue/RunDetail.vue` | Подробности запуска, бывший Processing/RunDetail |
| `PhotoSorter/frontend/src/features/queue/RunProgress.vue` | Статистика прогресса отдельной ФО |
| `PhotoSorter/frontend/src/features/settings/AppearanceSettings.vue` | Тема |
| `PhotoSorter/frontend/src/features/settings/UploadSettings.vue` | Параллельность загрузки |
| `PhotoSorter/frontend/src/features/settings/MegaLocSettings.vue` | CPU и автозапуск, установка модели |
| `PhotoSorter/frontend/src/features/settings/StorageSettings.vue` | Использование места, сроки и очистка |
| `PhotoSorter/frontend/src/features/settings/SystemSettings.vue` | API, worker, логи |
| `PhotoSorter/backend/server/services/archives.py` | Атомарный переиспользуемый ZIP |
| `PhotoSorter/backend/server/services/compute_settings.py` | CPU настройка из БД, перед следующим заданием |
| `PhotoSorter/backend/server/db/migrations/0018_cpu_threads.sql` | Параметр CPU |

Удалены старые `ProcessingView/Overview/History`, старый
`processingDashboard.ts` и панель `ReferencePreparationStatus.vue`.

## Новые модули

| Модуль | Ответственность |
|---|---|
| `backend/server/services/archive_pipeline.py` | Полный ZIP как последний этап MegaLoc, проценты |
| `backend/server/services/archive_retries.py` | Долговременное повторение ZIP без MegaLoc |
| `backend/server/services/retention.py` | Настраиваемые сроки хранения, безопасные дедлайны |
| `backend/server/db/migrations/0019_retention_preferences.sql` | Глобальная политика удаления |
| `backend/server/db/migrations/0020_workload_threads.sql` | Раздельные FO/reference CPU потоки |
| `backend/server/db/migrations/0021_archive_retry.sql` | PostgreSQL очередь повтора ZIP |
| `frontend/src/features/settings/PerformanceSettings.vue` | Режимы и CPU по задачам |
| `frontend/src/styles/reference-layout.css` | Исправление вертикальной компоновки галереи образцов |
