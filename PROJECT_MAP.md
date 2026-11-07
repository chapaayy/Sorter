# PROJECT_MAP.md — текущая архитектура PhotoSorter

```text
Браузер: один Vue 3 SPA (/)
  ├─ /fo              Фотоотчёты, загрузка партий, просмотр
  ├─ /references      Библиотека конструкций: массовый импорт и добавление фото
  ├─ /processing      Очередь MegaLoc, запуск/остановка
  ├─ /results         Галереи результатов, ZIP, подтверждение
  ├─ /logs            Логи и фильтры
  ├─ /settings        Темы, диск, жизненный цикл, состояние служб
  └─ /login           Авторизация
         │ HTTPS, same-origin /api/*
         ▼
Caddy (:80/:443) ──────► FastAPI (api:8000, один процесс)
                              │ server/main.py
                              ├─ server/api/routes/site.py  => Vue dist на / и /assets/*
                              ├─ server/api/routes/auth.py  => sessions/auth.py
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

**Образцы:** Vue `ReferenceDirectoryImporter` → проверка всех файлов в браузере → `POST /api/references/import/preview` → сверка город/номер/адрес с БД → передача через общий `useReferenceTransfer` и `/api/uploads` → SHA-256/Pillow → дополняем существующие конструкции или создаём новые. `ReferencePhotoUploader` добавляет обычные фото в выбранную конструкцию. Адрес хранится отдельно в `reference_constructions`, стабильный идентификатор не меняется. Старые `SAM-xxxx` записи остаются без миграции. [Инструкция](docs/REFERENCE_IMPORT.md).

**Upload / восстановление:** Vue `UploadPanel` → `/api/batches` → регистрация точного набора ожидаемых файлов через `PUT /api/batches/{id}/upload-manifest` (новые партии) → `/api/uploads` (16 МиБ PATCH, идемпотентное POST создание через `client_upload_id` из манифеста) → повторяем сетевые ошибки с backoff и возможностью «Пауза», считываем фактическое смещение, докачиваем только отсутствующие байты → `finish` с проверкой Pillow/SHA-256 → постоянный оригинал в `data/uploads/`, запись PostgreSQL, thumbnail queue. Состояние `waiting/complete` хранится в batches; ожидаемые UUID/пути/размеры — `batch_upload_manifest_files`. После каждой финализации сервер сверяет ВСЕ ожидаемые файлы, при полном наборе подтверждает завершение транзакционно. Старые партии без манифеста идут по прежнему пути. Обработка запрещена до `complete`, а автоматическая постановка в очередь включается лишь для новых партий с opt-in (этап 2). При потере соединения или перезагрузке вкладки `PendingUploads` читает `GET /api/batches/{id}/pending`, автоматически завершает полностью переданные файлы; для неполного пользователь заново выбирает оригинал и его SHA-256 всей уже переданной части сверяется перед дозагрузкой. Отмена доступна только для незавершённой передачи. Готовность партии и причины блокировки отображаются в разделе «ФО»; панель «Обработка» предназначена для мониторинга MegaLoc.

**Панель обработки (этап 4):** `ProcessingView.vue` читает активные задания через фильтр существующего `/api/runs?scope=active` и `/api/system/status` каждые 4 секунды; историю `/api/runs?scope=history` — реже. Состояние модели, heartbeat Worker и сохранённые настройки читаются через существующие API. `ProcessingOverview.vue`, `ProcessingQueue.vue`, `ProcessingHistory.vue` и `utils/processingDashboard.ts` изолируют отображение; единый `RunProgress.vue` показывает только измеренный прогресс. Запуск и повтор выполняются в ФО, остановка — через существующий API с подтверждением. Ручные VPN/Worker сценарии описаны в `docs/STAGE4_ACCEPTANCE.md`.

**Интерфейс ФО и история MegaLoc (этап 3):** `services/batch_runs.py` собирает из `jobs` последний запуск (актуальный статус из столбца `status`, прогресс из JSON snapshot) и последний опубликованный успешный/частично успешный результат; новые `latest_run`, `last_result_run_id` доступны в `/batches` и `/batches/{id}` без файловых путей. `GET /batches/{id}/runs` возвращает историю по этой партии (пагинация), включая старые успехи. Vue `FoBatchCard` и `FoGallery` используют один чистый helper `utils/batchProcessing.ts` и `BatchProcessingStatus.vue` для статусов, достоверных счётчиков/процентов, номера очереди, переходов к результатам и кнопок. «Остановить» для queued и running — существующий `/runs/{id}/stop` с подтверждением. Состояния миниатюр и MegaLoc не смешиваются; сохранённые предыдущие результаты остаются доступны в отдельной истории.

**Автоматическая обработка (этап 2):** `processing_settings` хранит настройку «обрабатывать новые партии» (default OFF) и порог. `UploadPanel` передаёт индивидуальный opt-in и порог при регистрации нового манифеста; `batches.auto_process_state` хранит `waiting/queued/cancelled/manual`, а `auto_process_run_id` — созданный job. Служба `cleanup` независимо от браузера сканирует только `waiting + manifest complete`, повторно проверяет файлы на диске и под глобальной advisory-блокировкой `723409133` и FOR UPDATE создаёт задачу через единую функцию `jobs._enqueue_locked` — тот же путь, что ручной `/api/runs`. Создание job и фиксация `queued`/ID — одна транзакция. Очередь полна/нет SAM → сохранённое ожидание без повторного создания job; ошибка выполненного job автоматически не перезапускается. Только новый manifest opt-in: никакого автоматического обхода старых партий/результатов. `POST /batches/{id}/auto-processing/cancel` отменяет лишь ожидание до enqueue.

**Распознавание:** `/api/runs` → PostgreSQL FIFO и single-leader → MegaLoc **сначала группирует ФО**, затем независимо сравнивает группы с SAM → manifest, Hard Links или безопасные копии → `data/outputs/<run>/` → галерея результатов.

**ZIP/retention:** streaming ZIP под operation lease → пользователь отдельно подтверждает сохранение → срок `+2` календарных месяца UTC → `cleanup` после проверки leases/tasks. Shared SAM/Models не удаляются вместе с партией.

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

## Reference queue — этап 1, без изменения runtime

`server/db/migrations/0011..0013` → новые таблицы sessions, work_queue, reference versions/notices. `server/services/reference_versions.py` → проверяемая однократная V1 metadata в `database.initialize()`. `server/db/repositories/{reference_imports,reference_versions,work_queue}.py` → пассивные операции. Старые `jobs.py` и `worker.py` пока остаются единственным исполняемым планировщиком. Подробности: `docs/REFERENCE_QUEUE_STAGE1.md`.

## Изолированный импорт образцов (этап 2)

`api/routes/reference_imports.py` (gated JSON/byte HTTP) → `services/reference_imports.py` (манифест, состояния, завершение, enqueue) + `services/reference_uploads.py` (части, SHA, duplicate receipt) → `db/repositories/reference_imports.py` (SQL, FIFO) и `storage/reference_objects.py` (изолированный staging, immutable links). `frontend/src/api/referenceImports.ts` — контракты клиента, **пока без подключения к существующему UI**. Миграция `0014_reference_import_transfers.sql`. Только завершённая сессия создаёт future prep job, текущий worker остаётся прежним.
