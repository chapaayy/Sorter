# FILE_INDEX.md — актуальный индекс значимых файлов

Правило: новый модуль регистрировать здесь с назначением и потребителем. Пустые `__init__.py`/служебные `.gitkeep` не перечисляются отдельно.

| Файл / каталог | Ответственность / кто использует |
|---|---|
| `compose.yaml` | Docker caddy/api/worker/cleanup/postgres и mounts; оператор |
| `install.sh` | установка без регенерации секретов; оператор |
| `.env.example`, `.gitignore`, `.dockerignore` | DOMAIN и исключение секретов/данных/весов; Git/Docker |
| `.github/workflows/ci.yml` | Python compile, pytest и тестовая PostgreSQL; GitHub CI |
| `Models/models/`, `Models/cache/` | модель и служебный кэш, вне Git; inference/model_store |
| `PhotoSorter/docker/app/Dockerfile` | CPU PyTorch/Python image; Compose |
| `PhotoSorter/docker/caddy/Caddyfile` | HTTPS reverse proxy; Caddy |
| `PhotoSorter/requirements*.txt` | Python базовые и серверные зависимости; image |
| `PhotoSorter/backend/app/config.py` | пути Models/data/runs; все backend сервисы |
| `app/photos/{reader,scanner,labels}.py` | форматы/сканирование/валидация SAM; MegaLoc, uploads |
| `app/recognition/pipeline.py` | неизменённый ФО→группы→SAM; CPU Worker |
| `app/recognition/grouping/finder.py` | неизменённые группы cosine; pipeline |
| `app/recognition/matching/resolver.py` | неизменённое назначение SAM; pipeline |
| `app/recognition/math.py` | векторная математика; grouping/matching |
| `app/recognition/engines/{base.py,megaloc/}` | MegaLoc loader/extractor; CPU Worker |
| `app/recognition/errors.py` | отмена inference; worker/pipeline |
| `app/jobs/{overall_progress,progress,runtime,worker}.py` | прогресс, lifecycle одного inference; server/worker |
| `app/results/copier.py` | именование эксклюзивных фото outputs; repository |
| `app/results/repository.py` | атомарная публикация, manifest index, read runs; result routes/Worker |
| `app/results/exporter.py` | JSON/CSV manifest и атомарный JSON; repository |
| `app/logging/events.py` | JSONL события по run; runtime/logs route |
| `app/system/{downloads,model_store,performance}.py` | получение весов, подпись, CPU параметры; model routes/engine |
| `server/main.py` | сборка FastAPI, lifespan, middleware, health; uvicorn |
| `server/auth.py` | scrypt/session/origin; auth route/middleware |
| `server/database.py` | legacy schema, connect, init и snapshots; services/jobs |
| `server/db/migration_runner.py` | versioned forward-only SQL; database.initialize |
| `server/db/repositories/batches.py` | batch/photo metadata queries; services/batches.py |
| `server/db/migrations/0001_batch_lifecycle.sql` | display_name, retention, leases, cleanup tracking; runner |
| `server/db/migrations/0002_batch_upload_state.sql` | обратимо-совместимое определение open/ready/sealed для исторических партий; runner |
| `server/uploads.py` | legacy resumable API/sha+Pillow+direct transfer; main и UI |
| `server/jobs.py` | старый `/api/runs` и stop; main, worker |
| `server/worker.py` | последовательное выполнение MegaLoc; Compose worker |
| `server/reference_cache.py` | **только** reference embeddings; MegaLoc Worker |
| `server/api/routes/auth.py` | login/logout/me; main |
| `server/api/routes/batches.py` | batch CRUD, photo removal, retention/delete HTTP; main |
| `server/api/routes/models.py` | модель/загрузка; main |
| `server/api/routes/results.py` | read model/run manifests; main, image/download routes |
| `server/api/routes/images.py` | ограниченная выдача оригиналов; main/download |
| `server/api/routes/downloads.py` | streaming ZIP + lease; main |
| `server/api/routes/logs.py` | прежние run JSONL events; main |
| `server/api/routes/storage.py` | mount usage API; main |
| `server/api/routes/site.py` | единственный Vue SPA `/`, безопасные `/assets/*` и history fallback; main |
| `server/services/batches.py` | batch list/create/rename/photos, до-run photo removal; batch route |
| `server/services/operations.py` | persistent live IO lease for batch; uploads/ZIP/cleanup |
| `server/services/retention.py` | confirmation/extend/status/due UTC; batch route/cleanup |
| `server/services/cleanup.py` | scoped resumable deletion; batch route + maintenance worker |
| `server/services/storage_usage.py` | mount and inode-based disk sizes; storage route |
| `server/storage/paths.py` | UUID/run validation and path ownership; batch/cleanup |
| `server/storage/hardlinks.py` | exclusive hardlink/fallback/checksum; app/results/copier |
| `server/workers/cleanup.py` | independent periodic retention/cleanup; Compose cleanup |
| `PhotoSorter/backend/tests/test_grouping.py` | MegaLoc grouping baseline (math unchanged); pytest |
| `PhotoSorter/backend/tests/test_progress_ring.py` | progress/ETA regression; pytest |
| `PhotoSorter/backend/tests/test_stage1_lifecycle.py` | schema, hardlink, delete, lease, ZIP/retention; pytest |
| `PhotoSorter/docs/DEPLOYMENT.md` | legacy operator note, переадресация к root docs |
| `docs/ARCHITECTURE.md` | компоненты/границы/ограничения |
| `docs/DATA_LIFECYCLE.md` | ownership/state machines/retention |
| `docs/API.md` | актуальные и совместимые endpoints |
| `docs/DEPLOYMENT.md` | staging-only rollout/infrastructure safety |
| `docs/TESTING.md` | команды и матрица регрессий |
| `docs/BACKUP_RESTORE.md` | pg_dump/files, restore на изолированном стенде |
| `docs/ROLLBACK.md` | кодовый rollback без потери данных |
| `docs/MIGRATION_NOTES.md` | исходный и новый schema/path mapping |
| `docs/DESIGN_SYSTEM.md` | утверждённый будущий UX (этап 3) |

## Stage 2 — новые файлы и роли

| Файл | Назначение / кто использует |
|---|---|
| `server/db/migrations/0003_thumbnails_queue.sql` | thumbnail queue, updated_at/backfill |
| `server/db/migrations/0004_megaloc_queue.sql` | FIFO timestamps, queue indexes |
| `server/db/migrations/0005_result_pages.sql` | индекс finalized FO source lookup |
| `server/db/migrations/0006_unfinished_age.sql` | индекс unfinished TTL |
| `server/db/repositories/queue.py` | очередь/позиция/claim/один running; jobs/worker |
| `server/db/repositories/pagination.py` | keyset cursor для ФО/Образцов |
| `server/storage/thumbnail_cache.py` | версия/ключ/путь и политика WebP |
| `server/services/thumbnails.py` | enqueue/claim/render/retry/cache; upload/worker |
| `server/services/thumbnail_gc.py` | cache owner cleanup; maintenance |
| `server/services/disk_guard.py` | free-reserve admission; uploads/system |
| `server/services/temp_cleanup.py` | безопасный TTL только незавершённых .part; maintenance |
| `server/services/result_pages.py` | постраничные JSONL results; results router |
| `server/api/routes/thumbnails.py` | UUID WebP/202/status/retry; main |
| `server/api/routes/references.py` | SAM cursor gallery; main |
| `server/api/routes/originals.py` | оригинал по UUID с lease; main |
| `server/api/routes/system.py` | queue/latency/storage system status; main |
| `server/workers/thumbnail.py` | отдельный low-priority process; Docker |
| `PhotoSorter/tools/benchmark_api.py` | read-only stage A/B latency sampler |
| `PhotoSorter/backend/tests/test_stage2_platform.py` | thumbnails/FIFO/cursor/logs/storage tests |
| `PhotoSorter/backend/tests/test_stage2_transfers.py` | PUT/PATCH/cancel/ZIP/original stream tests |
| `docs/PERFORMANCE.md` | CPU A/B метод и ограничения |
| `docs/OPERATIONS.md` | Queue, retention, logs, preview, disk runbook |

## Основные изменённые файлы этапа 2

- `compose.yaml` — thumbnail сервис, CPU budget, Docker log rotation.
- `server/uploads.py` — постановка миниатюр, контроль диска, отмена .part, updated_at.
- `server/jobs.py`/`server/worker.py`/`server/database.py` — FIFO queue и лидер, безопасный stop.
- `server/main.py` — дополнительные routers и измерение response latency.
- `server/api/routes/{batches,results,logs,downloads}.py` — cursor/leases/совместимость.
- `server/services/storage_usage.py` — inode dedup, DB estimated bytes, диск.
- `server/workers/cleanup.py` — редкая очистка thumbnail/temp.
- `app/results/exporter.py` — `manifest.rows.jsonl` параллельно старым JSON/CSV.
- `app/logging/events.py` — ротация, cursor API.
- `app/jobs/progress.py` — измеряемая скорость по стадиям.
- `.github/workflows/ci.yml` — stage2 workflow.

## Stage 3 — новые Vue/TypeScript файлы и серверный мост

| Модуль | Ответственность |
|---|---|
| `frontend/{package.json,package-lock.json,vite.config.ts,tsconfig.json,index.html}` | точные зависимости, Vite `/`, строгая сборка |
| `frontend/src/main.ts` | bootstrap Vue 3, Pinia, router |
| `frontend/src/app/{App.vue,router.ts}` | auth gate, маршруты всех 6 разделов |
| `frontend/src/api/{client,batches,references,runs,results,logs,system}.ts` | cookie-safe typed API и пагинация; единственный network boundary |
| `frontend/src/stores/{theme,session,notice}.ts` | тема, httpOnly-сессия, уведомления |
| `frontend/src/composables/{useCursor,usePolling}.ts` | хранение страниц и polling без параллельных запросов |
| `frontend/src/components/layout/Shell.vue` | шесть разделов, responsive sidebar |
| `frontend/src/components/ui/*.vue` | RowCard 108 px, UiButton, PageHeader, ConfirmDialog, Toast, EmptyState |
| `frontend/src/components/gallery/*.vue` | lazy preview и полноразмерный viewer |
| `frontend/src/components/split/GroupPicker.vue` | desktop dual-pane / mobile select |
| `frontend/src/features/auth/LoginView.vue` | cookie auth form |
| `frontend/src/features/fo/{FoList,FoGallery,UploadPanel}.vue` | папки, партии, отдельная галерея, удаление |
| `frontend/src/features/references/{ReferenceLibrary,ReferenceUploader}.vue` | библиотека SAM, редактирование, сетевая загрузка |
| `frontend/src/features/processing/{ProcessingView,RunDetail,RunProgress}.vue` | очередь MegaLoc, измеренные стадии, стоп |
| `frontend/src/features/results/{ResultsList,ResultDetail}.vue` | SAM/groups, ZIP, подтверждение, retention |
| `frontend/src/features/logs/LogsView.vue` | курсорные логи, tail, копирование |
| `frontend/src/features/settings/SettingsView.vue` | темы, состояние mount, безопасная очистка, срок хранения |
| `frontend/src/utils/{format,upload}.ts` | форматирование и resumable direct+PATCH |
| `frontend/src/styles/{tokens,base,components}.css` | graphite/light design tokens, responsive layout |
| `frontend/tests/*.test.ts` | Vitest unit contracts |
| `frontend/e2e/*.spec.ts`, `frontend/playwright.config.ts` | browser smoke journey: Chromium / WebKit / mobile |
| `backend/server/services/references.py` | owner-safe SAM rename/delete/cache query; no photo inference |
| `backend/server/api/routes/references.py` | SAM HTTP endpoints |
| `backend/server/api/routes/site.py` | single Vue `/` + `/assets/*`, retired paths 404 |
| `backend/server/services/batches.py` | aggregated counters for list rows |
| `backend/server/api/routes/logs.py` / `app/logging/events.py` | log tail pagination |
| `backend/server/api/routes/system.py` | owner-safe manual orphaned thumbnail cleanup |
| `backend/tests/test_stage3_ui_api.py` | SAM deletion/rename + SPA path isolation test |
| `docker/app/Dockerfile` | Node24 build stage, Python runtime |
| `.github/workflows/stage3-vue.yml` | npm ci + vue-tsc/Vite + Vitest + Playwright |

| `frontend/src/components/gallery/VirtualThumbnailGrid.vue` | Intersection/viewport-based virtual row window, rendering only visible FO/SAM/results cards (keeps full index for viewer) |

## Stage 4 — каталог новых модулей

| Файл | Ответственность |
|---|---|
| `PhotoSorter/backend/server/security/login_throttle.py` | Ограничение неверных логинов в single-process API, хэшированные ключи |
| `PhotoSorter/backend/server/security/__init__.py` | Пакет security primitives |
| `PhotoSorter/backend/server/services/heartbeat.py` | Запись процессов, вычисление свежести, фоновые потоки |
| `PhotoSorter/backend/server/db/migrations/0007_service_heartbeat.sql` | Новая отдельная таблица service_heartbeats, additive migration |
| `PhotoSorter/backend/server/db/migration_runner.py` | Игнорировать полнострочные SQL комментарии при разбивке простых SQL миграций |
| `PhotoSorter/backend/server/worker.py` | MegaLoc inference + роль worker heartbeat |
| `PhotoSorter/backend/server/workers/thumbnail.py` | Preview queue consumer + heartbeat |
| `PhotoSorter/backend/server/workers/cleanup.py` | Retention/GC worker + heartbeat |
| `PhotoSorter/backend/server/api/routes/system.py` | API живых heartbeat statuses для UI |
| `PhotoSorter/backend/server/api/routes/downloads.py` | ZIP path member validation, сохранён поток и lease |
| `PhotoSorter/backend/server/services/references.py` | Reject mutation of SAM referenced by historical published manifests |
| `PhotoSorter/backend/server/uploads.py` | Pillow upload pixel cap before finalizing |
| `PhotoSorter/frontend/src/types/api.ts` | Контракт heartbeat JSON |
| `PhotoSorter/frontend/src/features/settings/SettingsView.vue` | Реальная индикация живых megaloc,thumbnail,cleanup |
| `PhotoSorter/tools/stage4/snapshot.py` | Consistent PG custom-format + independent filesystem full backup, SHA, hardlinks, verify, isolated restore |
| `PhotoSorter/tools/stage4/ci_restore_drill.py` | Real disposable PG backup/restore in GitHub CI, restored file hash/inode checks |
| `PhotoSorter/tools/stage4/compare_baseline.py` | Проверка verified/golden MegaLoc SAM/group/rankings/score и ZIP CRC |
| `PhotoSorter/tools/stage4/staging_probe.py` | GET-only concurrency/p50/p95/rps and worker/disk monitoring |
| `PhotoSorter/backend/tests/test_stage4_security.py` | Zip Slip, SAM path, pixel cap, rate limit |
| `PhotoSorter/backend/tests/test_stage4_snapshots.py` | Synthetic hardlink archive/restore/secret safeguards |
| `PhotoSorter/backend/tests/test_stage4_installer.py` | Mocked Docker installer, no credential reset |
| `PhotoSorter/backend/tests/test_stage4_load.py` | Synthetic 1315 FO cursor/ZIP/cleanup; retention UTC calendar edges |
| `PhotoSorter/backend/tests/test_stage4_baseline.py` | Golden diff and ZIP mismatch detection |
| `PhotoSorter/backend/tests/test_stage4_heartbeat.py` | Worker fresh/stale status |
| `PhotoSorter/backend/tests/test_stage4_probe.py` | GET-only local threaded HTTP service for latency |
| `PhotoSorter/backend/tests/test_stage4_migration.py` | Semicolons in SQL comment do not break additive migrations |
| `install.sh` | Safe check, backup-gated update, preserve secrets and existing data UID |
| `.github/workflows/stage4-validation.yml` | Backend/DB/Compose/Caddy, disposable PG restoration, Vue/Chromium/WebKit jobs |
| `docs/STAGE4_ACCEPTANCE.md` | Финальные P0/P1 приёмочные условия и блокеры |
| `docs/STAGE4_ROLLOUT.md` | Ручной staging→production workflow только после разрешения |
| `docs/STAGE4_SECURITY.md` | Аудит и ограничения security |
| `docs/CHANGELOG.md` | Что сделано по 4 этапам |
