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
| `server/db/migrations/0001_batch_lifecycle.sql` | display_name, retention, leases, cleanup tracking; runner |
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
| `server/api/routes/site.py` | старый index/static; main |
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
| `PhotoSorter/frontend/static/{index.html,app.js,style.css}` | **текущий**, пока не заменённый frontend; FastAPI site |
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
