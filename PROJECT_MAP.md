# PROJECT_MAP.md — архитектурная карта

```text
Browser (legacy / and opt-in Vue /v3/)
    | HTTPS/Caddy
    v
FastAPI server/main.py (lifespan, session+Origin middleware)
    |-- api/routes/auth.py          => auth.py => users/sessions
    |-- api/routes/batches.py       => services/batches.py,retention.py,cleanup.py
    |-- uploads.py (legacy adapter) => operations leases, uploads table, incoming/ -> uploads/
    |-- jobs.py                     => jobs table, Job snapshot, run enqueue/stop
    |-- api/routes/models.py        => model_store/downloads
    |-- api/routes/results.py       => app/results/repository.py => manifest
    |-- api/routes/images.py        => read-only photo path guards
    |-- api/routes/downloads.py     => zipstream + operations lease
    |-- api/routes/logs.py          => events.jsonl
    |-- api/routes/storage.py       => services/storage_usage.py
    |-- api/routes/site.py          => old frontend/static/*
    |
PostgreSQL (server/database.py + db/migration_runner.py + migrations/)
    |-- batches,uploads,jobs,users,sessions,reference_cache (legacy retained)
    |-- schema_migrations,download_confirmations,batch_operations,cleanup_tasks
    |-- db/repositories/batches.py   => SQL reads/writes separated from services
    |
    +-- server/worker.py            => app/jobs/* => app/recognition/* (unchanged)
    |      |                         => app/results/copier.py => storage/hardlinks.py
    |      +-- outputs/<run>/megaloc/{SAM,_Неопределено}/ + manifest
    |
    +-- server/workers/cleanup.py   => services/cleanup.py,retention.py
           +-- runs/<run> outputs/<run> uploads/<batch> incoming/<upload>.part
               NEVER references/ or Models/
```

**Физические корни:** `Models/models` — веса, `Models/cache` — загрузчики; `PhotoSorter/data` — persistent originals/outputs/runs/references; PostgreSQL — отдельный Docker volume. Контейнеры: `caddy`, `api`, `worker`, `cleanup`, `postgres`.

## Потоки данных

- **Upload:** `POST /api/batches` → `POST /api/uploads` или direct PUT → PATCH/offset (при обрыве) → `finish` (Pillow+SHA) → `uploads/<UUID>/`; открытая IO-операция учитывается в БД.
- **Run:** `POST /api/runs` → `jobs` в PostgreSQL → единственный Worker → неизменённый MegaLoc → временный output → верифицированные hardlinks → manifest → атомарная публикация.
- **Просмотр/ZIP:** manifest → защищённый photo path → `zipstream-ng` (без дискового ZIP) → клиент. При ZIP поток удерживает lease.
- **Подтверждение:** пользователь сохраняет весь ZIP → отдельный POST подтверждения → `delete_after_at` через 2 calendar months UTC.
- **Удаление:** DELETE batch / достижение срока → `deleting` → остановка jobs, ожидание IO → проверка trusted IDs/paths → все owned files → строки jobs/uploads → tombstone `deleted`. Crash возобновляется через `cleanup_tasks`.

См. [DATA_LIFECYCLE](docs/DATA_LIFECYCLE.md), [API](docs/API.md), [FILE_INDEX](FILE_INDEX.md). **Этап 2 серверно реализован**: preview-очередь, FIFO jobs, журнал и дисковая защита. Этап 3 — Vue UI, этап 4 — полномасштабная проверка/production.

## Новые потоки этапа 2

```text
Upload finish (Pillow+SHA) --SQL txn--> thumbnail_tasks(queue)
       |                                |
       +--> original uploads/            +--> server/workers/thumbnail.py
                                                   |
                                      storage/thumbnail_cache.py
                                                   |
                                    data/cache/thumbnails/v1/<checksum>.webp
Cursor galleries  -> db/repositories/pagination.py -> uploads metadata
Result galleries  -> services/result_pages.py -> manifest.rows.jsonl (new)
Original viewer   -> api/routes/originals.py -> operation lease + file stream
Jobs API          -> db/repositories/queue.py -> PostgreSQL FIFO
Worker            -> session advisory leader -> exactly one running inference
Logs              -> app/logging/events.py -> rotated JSONL + cursor
Maintenance       -> temp_cleanup / thumbnail_gc (time-limited, owned only)
System API        -> p50/p95 request latency, job/preview queue, disk reserve
```

Общие `references/` и `Models/` не принадлежат партиям и не затрагиваются при cleanup. Для storage, Docker services и CPU см. `docs/OPERATIONS.md`.

## Stage 3 — frontend application graph

```text
PhotoSorter/frontend/
  package.json / package-lock.json / vite.config.ts / tsconfig.json
  index.html
  src/
    main.ts             -> Vue + Pinia + Vue Router + global styles
    app/                 -> App.vue auth gate + router.ts
    api/                 -> typed client / batches / references / runs / results / logs / system
    stores/              -> session / theme / notifications
    composables/         -> usePolling / useCursor
    components/
      layout/Shell.vue   -> sidebar six routes + mobile drawer
      ui/                -> RowCard, Buttons, PageHeader, ConfirmDialog, EmptyState, ToastStack
      split/             -> GroupPicker (desktop left / mobile select)
      gallery/           -> ThumbnailGrid lazy WebP, ImageViewer full image
    features/
      auth/              -> LoginView
      fo/                -> FoList, FoGallery, UploadPanel
      references/        -> ReferenceLibrary, ReferenceUploader
      processing/        -> ProcessingView, RunDetail, RunProgress
      results/           -> ResultsList, ResultDetail
      logs/              -> LogsView
      settings/          -> SettingsView
    utils/               -> format, resumable upload
    styles/              -> graphite/light tokens, base, reusable layout
  tests/                 -> Vitest contracts/format/upload
  e2e/                   -> Playwright mocked API navigation and flows
  dist/ (generated)      -> static assets, not tracked
```

`server/api/routes/site.py` раздельно выдаёт `/` (legacy) и `/v3/` (Vue SPA history fallback), `/v3/assets` только внутри `frontend/dist/assets`. Python Dockerfile использует multi-stage Node 24 build; runtime без Node. `server/services/references.py` + `api/routes/references.py` обеспечивают явные управляемые rename/delete/cache SAM. `system/cache/cleanup` очищает только orphaned previews.

## Stage 4 — validation, workers, recovery

```text
server/security/login_throttle.py     -> bounded login failure memory; auth.py/login
server/services/heartbeat.py          -> 10s role pulse + fresh/stale API state
server/db/migrations/0007_service_heartbeat.sql -> additive table
  server/worker.py                    -> MegaLoc heartbeat (separate daemon thread)
  server/workers/thumbnail.py         -> independent preview heartbeat
  server/workers/cleanup.py           -> independent retention heartbeat
server/api/routes/system.py           -> system/status.services.<role>.alive
frontend/features/settings            -> honest health indicator for all 3 services
server/api/routes/downloads.py        -> strict safe ZIP member names
server/services/references.py         -> historic manifest SAM guard
server/uploads.py                     -> 30M pixel upload limit
install.sh                            -> --check and upgrade approval, preserve secrets
PhotoSorter/tools/stage4/
  snapshot.py                         -> independent backup, hash verify, test restore
  ci_restore_drill.py                 -> disposable real PG17 dump/restore
  compare_baseline.py                 -> actual/golden MegaLoc manifest + ZIP diff
  staging_probe.py                    -> read-only HTTP latency/disk/worker stats
backend/tests/test_stage4_*.py        -> disposable Linux/PG CI regressions
.github/workflows/stage4-validation.yml -> 3 jobs: backend/Caddy, restore, Vue/WebKit
```

Ни одна из утилит не переносит реальные `Models`/фотографии и не запускает deployment без оператора. Без реальных staging acceptance-метрик production остаётся закрытым.
