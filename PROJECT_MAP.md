# PROJECT_MAP.md — текущая архитектура PhotoSorter

```text
Браузер: один Vue 3 SPA (/)
  ├─ /fo              Фотоотчёты, загрузка партий, просмотр
  ├─ /references      Библиотека конструкций: массовый импорт и добавление фото
  ├─ /queue           Единая FIFO: ФО и подготовка эталонов
  ├─ /results         Галереи результатов, готовые ZIP
  ├─ /logs            Логи и фильтры
  ├─ /settings        Темы, диск, жизненный цикл, состояние служб
  └─ /login, /register   Авторизация и заявка на доступ
         │ HTTPS, same-origin /api/*
         ▼
Caddy (:80/:443) ──────► FastAPI (api:8000, один процесс)
                              │ server/main.py
                              ├─ server/api/routes/site.py  => Vue dist на / и /assets/*
                              ├─ server/api/routes/auth.py  => server/auth.py
                              ├─ server/api/routes/batches.py, uploads.py
                              │           │
                              │           └─ services/batches.py, operations.py
                              ├─ server/api/routes/references.py
                              │           ├─ services/references.py
                              │           └─ services/construction_catalog.py
                              ├─ jobs.py + api/routes/results.py
                              │           └─ db/repositories/queue.py
                              ├─ api/routes/images.py, originals.py, thumbnails.py
                              ├─ api/routes/downloads.py  => verified ZIP stream
                              ├─ api/routes/logs.py, models.py, storage.py, system.py
                              └─ db/migration_runner.py ───► PostgreSQL 17
                                                            users/sessions/batches/uploads/reference_constructions/
                                                            jobs/thumbnails/cleanup/service heartbeat

Параллельные процессы в том же Docker Compose:
  worker        ──► app/jobs/worker.py ──► app/recognition/ (MegaLoc, не менять)
                    │                       ├─ grouping (ФО)
                    │                       └─ matching (SAM)
                    └─ app/results/*        ──► safe hardlinks/ZIP manifests
  thumbnail     ──► services/thumbnails.py  ──► WebP cache
  cleanup       ──► services/cleanup.py, retention.py, temp_cleanup.py
                    └─ services/auto_processing.py → существующая jobs.py/queue.py
                    (проверка opt-in партий каждые ~30 сек, только owned files, без shared SAM/Models)

Постоянное состояние:
  Models/models/             веса MegaLoc
  Models/cache/              HuggingFace/torch caches
  PhotoSorter/data/          оригиналы, SAM, результаты, previews
  outdoor-sorter_postgres_data   PostgreSQL
  outdoor-sorter_caddy_data, caddy_config  TLS
```

## Распределение ответственности

| Слой | Место | Назначение |
|---|---|---|
| Vue app | `PhotoSorter/frontend/src/app/` | Auth gate, Vue history router, единый layout |
| Vue API | `PhotoSorter/frontend/src/api/` | Типизированные запросы по `/api` |
| Vue features | `PhotoSorter/frontend/src/features/` | Разделы и подстраницы без дублирования общего UI |
| Vue components | `PhotoSorter/frontend/src/components/` | Общие кнопки, modal, gallery, grid, свёрнутая desktop-панель и общий список GroupPicker |
| Vue stores | `PhotoSorter/frontend/src/stores/` | Сессия, theme, уведомления, локальное состояние бокового меню |
| Backend API | `PhotoSorter/backend/server/api/routes/` | HTTP контракты, проверка доступа |
| Backend services | `PhotoSorter/backend/server/services/` | Работа с состоянием, безопасное удаление, архивы, очередь |
| PostgreSQL | `PhotoSorter/backend/server/db/` | Аддитивные миграции и read/write репозитории |
| Storage | `PhotoSorter/backend/server/storage/` | Безопасные пути и Hard Links |
| Inference | `PhotoSorter/backend/app/recognition/` | **Замороженные** математические алгоритмы MegaLoc |
| Jobs | `PhotoSorter/backend/app/jobs/` | Стадии исполнения, прогресс и export |
| Docker | `compose.yaml`, `PhotoSorter/docker/` | Caddy + API + 3 worker services + PostgreSQL |
| Support | `PhotoSorter/tools/` | Benchmark, snapshot, verify, restore-test и CI smoke |
| CI | `.github/workflows/ci.yml` | Один pipeline для `main` |

## Основные сценарии

**Заявки на доступ:** `features/auth` → `api/routes/access_requests.py` → `services/access_requests.py` → репозиторий заявок и миграция 0024. Владелец выбирает готовые запуски в `features/settings/users`; одобрение создаёт аккаунт и разрешения в одной транзакции. `security/access_policy.py` ограничивает каталог, фото и ZIP конкретными разрешёнными запусками.

**Образцы:** Vue `ReferenceDirectoryImporter` → проверка всех файлов в браузере → `POST /api/references/import/preview` → сверка город/номер/адрес с БД → передача через общий `useReferenceTransfer` и `/api/uploads` → SHA-256/Pillow → дополняем существующие конструкции или создаём новые. `ReferencePhotoUploader` добавляет обычные фото в выбранную конструкцию. Адрес хранится отдельно в `reference_constructions`, стабильный идентификатор не меняется. Старые `SAM-xxxx` записи остаются без миграции. [Инструкция](docs/REFERENCE_IMPORT.md).

**Upload / восстановление:** Vue `UploadPanel` → `/api/batches` → регистрация точного набора ожидаемых файлов через `PUT /api/batches/{id}/upload-manifest` (новые партии) → `/api/uploads` (16 МиБ PATCH, идемпотентное POST создание через `client_upload_id` из манифеста) → повторяем сетевые ошибки с backoff и возможностью «Пауза», считываем фактическое смещение, докачиваем только отсутствующие байты → `finish` с проверкой Pillow/SHA-256 → постоянный оригинал в `data/uploads/`, запись PostgreSQL, thumbnail queue. Состояние `waiting/complete` хранится в batches; ожидаемые UUID/пути/размеры — `batch_upload_manifest_files`. После каждой финализации сервер сверяет ВСЕ ожидаемые файлы, при полном наборе подтверждает завершение транзакционно. Старые партии без манифеста идут по прежнему пути. Обработка запрещена до `complete`, а автоматическая постановка в очередь включается лишь для новых партий с opt-in (этап 2). При потере соединения или перезагрузке вкладки `PendingUploads` читает `GET /api/batches/{id}/pending`, автоматически завершает полностью переданные файлы; для неполного пользователь заново выбирает оригинал и его SHA-256 всей уже переданной части сверяется перед дозагрузкой. Отмена доступна только для незавершённой передачи. Готовность партии и причины блокировки отображаются в разделе «ФО»; панель «Обработка» предназначена для мониторинга MegaLoc.


**Интерфейс ФО и история MegaLoc (этап 3):** `services/batch_runs.py` собирает из `jobs` последний запуск (актуальный статус из столбца `status`, прогресс из JSON snapshot) и последний опубликованный успешный/частично успешный результат; новые `latest_run`, `last_result_run_id` доступны в `/batches` и `/batches/{id}` без файловых путей. `GET /batches/{id}/runs` возвращает историю по этой партии (пагинация), включая старые успехи. Vue `FoBatchCard` и `FoGallery` используют один чистый helper `utils/batchProcessing.ts` и `BatchProcessingStatus.vue` для статусов, достоверных счётчиков/процентов, номера очереди, переходов к результатам и кнопок. «Остановить» для queued и running — существующий `/runs/{id}/stop` с подтверждением. Состояния миниатюр и MegaLoc не смешиваются; сохранённые предыдущие результаты остаются доступны в отдельной истории.

**Автоматическая обработка (этап 2):** `processing_settings` хранит настройку «обрабатывать новые партии» (default OFF) и порог. `UploadPanel` передаёт индивидуальный opt-in и порог при регистрации нового манифеста; `batches.auto_process_state` хранит `waiting/queued/cancelled/manual`, а `auto_process_run_id` — созданный job. Служба `cleanup` независимо от браузера сканирует только `waiting + manifest complete`, повторно проверяет файлы на диске и под глобальной advisory-блокировкой `723409133` и FOR UPDATE создаёт задачу через единую функцию `jobs._enqueue_locked` — тот же путь, что ручной `/api/runs`. Создание job и фиксация `queued`/ID — одна транзакция. Очередь полна/нет SAM → сохранённое ожидание без повторного создания job; ошибка выполненного job автоматически не перезапускается. Только новый manifest opt-in: никакого автоматического обхода старых партий/результатов. `POST /batches/{id}/auto-processing/cancel` отменяет лишь ожидание до enqueue.

**Распознавание:** `/api/runs` → PostgreSQL FIFO и single-leader → MegaLoc **сначала группирует ФО**, затем независимо сравнивает группы с SAM → manifest, Hard Links или безопасные копии → `data/outputs/<run>/` → галерея результатов.

**ZIP/retention:** MegaLoc → результаты → атомарный ZIP → завершено. Дедлайн удаления новых задач задаётся в настройках (2 месяца по умолчанию, от минуты). Cleanup учитывает IO leases, удаляет и архивы. ZIP-only retry без MegaLoc. Shared SAM/Models не удаляются вместе с партией.

**Бэкап:** отдельно сохраняются PostgreSQL, `PhotoSorter/data`, `Models`, env secrets и TLS Docker volumes. `snapshot.py` не сохраняет TLS volume, поэтому оператор архивирует его отдельно. Тест восстановления допустим только на изолированной пустой БД.

## Инварианты

- Веб-интерфейс **ровно один**: Vue SPA по `/`; старых `/v3/` и `/static/*` нет.
- Боковая навигация desktop сохраняет предпочтение `ps.sidebar.collapsed` локально; мобильный drawer работает независимо. Общий `GroupPicker` показывает одну строку на элемент, имеет регулируемую ширину desktop-колонки (перетаскивание или стрелки, сохранение в `ps.group-picker.width`), обрезает только текст, который не помещается даже при текущей ширине, и сохраняет полное название в подсказке.
- `PhotoSorter/frontend/dist/` собирается в Docker на Node 24, runtime использует Python/FastAPI, без сервера Node.
- Под `Models/` только веса/загрузчики, под `PhotoSorter/data/` пользовательские оригиналы и результаты; исходники из Git не пересоздают эти каталоги произвольно.
- Математику MegaLoc, бизнес-правила сохранения ZIP и защиту API не менять ради косметического рефакторинга.
- Глобальные настройки auto-MegaLoc в PostgreSQL, по умолчанию OFF. У каждой новой партии собственное решение и порог, зафиксированные в БД; терминальные и исторические задания автоматически не создаются снова.
- Для манифестных партий `pending=0` недостаточно: `complete` устанавливается только после финализации каждого зарегистрированного UUID и проверки наличия оригинала. Манифест неизменяем; потерянный ответ не создаёт новую запись. Файлы исходной папки повторно выбирает пользователь после закрытия браузера.
- Незавершённые `.part` остаются в БД до финализации или явной отмены (либо старой TTL-очистки). Ни авто-восстановление, ни отмена конкретной передачи не затрагивают  ранее финализированные ФО. Сохранение полномочий на выбранные локальные файлы после перезагрузки вкладки невозможно без нового выбора пользователя.

См. [Инструкция импорта образцов](docs/REFERENCE_IMPORT.md), [FILE_INDEX](FILE_INDEX.md), [AGENTS](AGENTS.md), [API](docs/API.md), [BACKUP_RESTORE](docs/BACKUP_RESTORE.md).


## Единая рабочая цепочка

```text
Vue /fo → manifest ФО → /api/uploads → uploads + batches
                                     └── auto_processing → jobs + work_queue(seq)
Vue /references → manifest образцов → /api/reference-imports
                                     ├── reference_import_sessions/files
                                     └── reference_staging/ → reference_preparation_jobs
                                                           └── work_queue(seq)
                         │
                         ▼
                    server/worker.py
                         ├─ fo_processing → frozen reference_version_members
                         │                  → app/jobs/worker.py → MegaLoc → outputs
                         └─ reference_preparation → workers/reference_prepare.py
                              ├─ reference_cache.py (SHA-256 + model signature)
                              ├─ services/reference_gallery.py (UI projection)
                              └─ services/reference_publication.py
                                    └─ one atomic current_version_id
```

`services/reference_imports.py` и `services/reference_uploads.py` отвечают
за manifest/докачку/дедупликацию, не за inference. `db/repositories/work_queue.py`
единственный диспетчер CPU; `db/repositories/job_status.py` лишь формирует
публичное состояние ФО. `services/references.py` предоставляет управление
опубликованными объектами с созданием новой версии.

`library_notice_cursors` + `reference_library_events` управляют
однократными уведомлениями о смене опубликованной версии.

Подробнее `docs/REFERENCE_PIPELINE.md`.


## Компактные карточки в трёх разделах

`FoList.vue` → `FoBatchCard.vue` → `CompactTaskCard.vue`

`QueueView.vue` → `QueueTaskRow.vue` → `CompactTaskCard.vue`

`ResultsList.vue` → `CompactTaskCard.vue`

Только один модуль `utils/queueEstimates.ts` рассчитывает примерные сроки
для всей очереди; CSS живёт отдельно в `styles/task-cards.css`.
Общие CSS-токены обеих тем не меняются; иконки, загрузки и действия остаются
реальными. Backend дополняет публичный API готовой миниатюрой, реальным
прогрессом FO и счётчиками фотографий, без N запросов на карточку.


## Актуальный интерфейс

```text
Shell
├─ UploadCenter (сворачиваемый диалог папок ФО, докачки и образцов)
├─ Фотографии -> FoList / FoGallery (маршруты /fo)
├─ Образцы -> ReferenceLibrary (два независимых scroll container)
├─ Очередь -> QueueView / RunDetail / RunProgress
├─ Результаты -> ResultsList / ResultDetail
├─ Логи -> LogsView
└─ Настройки -> SettingsView
   ├─ AppearanceSettings
   ├─ UploadSettings
   ├─ MegaLocSettings
   ├─ PerformanceSettings
   ├─ StorageSettings
   └─ SystemSettings
```

`features/processing` удалена как ненужная альтернативная UI-ветка.
`src/utils/processingDashboard.ts` удалён. Все подробности доступны
в `/queue/runs/:runId`. Вкладка «Очередь» показывает только активное
или историю по кнопке; слова FIFO оставлены только внутри кода.

Скачивание: `server/api/routes/downloads.py` ->
`server/services/archives.py` -> `FileResponse`. ZIP находится внутри
каталога данного запуска и автоматически удаляется при очистке партии.

## Последний этап и новые настройки

`server/worker.py` → `app/jobs/runtime.py` → MegaLoc + export → `services/archive_pipeline.py` → `archives.py` → `jobs.status=completed` + `retention.schedule` → `workers/cleanup.py` (после срока, с проверкой leases). При сбое ZIP: `archive_retries` (PostgreSQL) → `workers/cleanup.py` → ZIP-only без инференса.

`frontend/features/settings/PerformanceSettings.vue` хранит режим auto/manual и отдельные потоки ФО/образцов (применяются к следующим заданиям); лимиты Docker для миниатюр/cleanup пока только отображаются из Compose, не изменяются через API. `StorageSettings.vue` управляет автоудалением новых запусков. Отключение настройки блокирует даже ранее назначенное автоматическое удаление; при включении просроченные партии получают новый полный срок, а не удаляются все сразу. Ручное удаление партии независимо от настройки.

`GET /api/runs/{id}/archive/status` определяет доступность полного ZIP после обработки. `POST /api/runs/{id}/archive/retry` восстанавливает пропавший/недоделанный ZIP по сохранённым результатам без повторного MegaLoc; задание хранится в `archive_retries`, обрабатывается сервисом cleanup. Перед атомарным опубликованием ZIP проверяются количество файлов и CRC. Новые UI-уведомления и кнопки восстановления расположены в `RunDetail.vue` и `ResultDetail.vue`.


## Зависимости чистого VPS

`install.sh --deploy` проверяет домен, затем при отсутствии зависимостей вызывает `PhotoSorter/tools/maintenance/install_prerequisites.sh`. На Ubuntu/Debian модуль использует официальный apt-репозиторий Docker и ставит недостающие пакеты до создания секретов и контейнеров. Рабочая установка Docker остаётся без изменений. `--check` пакеты не устанавливает.

## TCP BBR на Linux-хосте

Установщик `install.sh --deploy` вызывает `PhotoSorter/tools/maintenance/setup_tcp_bbr.sh --apply` после preflight и до Docker Compose. Отдельный модуль включает BBR только при наличии поддержки ядра, сохраняет собственные drop-in в `/etc/sysctl.d` и `/etc/modules-load.d`, не меняет qdisc и контейнерные настройки прочих сервисов. В `compose.yaml` алгоритм явно устанавливается для отдельного сетевого пространства Caddy через `PHOTOSORTER_CADDY_TCP_CC`, который `install.sh` берёт из текущего алгоритма хоста после попытки включить BBR. `--check` ничего не изменяет; `--disable` удаляет только файлы PhotoSorter и возвращает `cubic`. `PHOTOSORTER_ENABLE_BBR=0` пропускает будущие попытки настройки, но не отменяет ранее установленный BBR.

## Производительность, каталог конструкций и статусы (2026-11-08)

`api/routes/processing_settings.py` → `services/compute_settings.py` → PostgreSQL `processing_settings` → единый `server/worker.py` → `services/worker_cpu_affinity.py` + `app/system/performance.py`. Настройка действует **со следующего задания** FIFO; оба вида обработки используют один budget. Контейнер Worker ограничен доступным cpuset на этапе установки. Другие контейнеры не помещаются в жёсткий системный cpuset. Thumbnail/cleanup имеют относительные CPU shares, без жёсткой квоты.

`ReferenceLibrary.vue` → `CreateConstructionDialog.vue` → `api/routes/references.py` → `services/construction_catalog.py` → `reference_constructions`. Пустой каталог независим от текущей версии признаков. Фото в индивидуальные конструкции по-прежнему идут через `useReferenceTransfer` → `reference_imports` → единую очередь подготовки → `reference_publication`, а массовый импорт сохраняет старую строгую валидацию.

`stores/deletion.ts` + серверный `batches.delete_state` → `FoBatchCard.vue`, `QueueTaskRow.vue`, `ResultsList.vue` → единый `CompactTaskCard.vue` со статусным outline. Для `deleting` фон красный; для `delete_failed` только красная обводка. ZIP не выделен отдельным статусом.
