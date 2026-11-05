# PROJECT_MAP.md — архитектурная карта

```text
Browser (legacy static JS, stage 3 => Vue)
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

См. [DATA_LIFECYCLE](docs/DATA_LIFECYCLE.md), [API](docs/API.md), [FILE_INDEX](FILE_INDEX.md). **Этап 2** добавит thumbnails и настоящую очередь; сейчас backend не притворяется, что они готовы.
