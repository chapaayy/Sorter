# Архитектура, этап 1

Исходное приложение было одним FastAPI `main.py` и modules `uploads/jobs/database`. После этапа 1 `server/main.py` выполняет только сборку приложения, middleware авторизации и lifecycle. `server/api/routes/*` имеют HTTP-контракты, `server/services/*` владеют batch/retention/cleanup/storage use cases, `server/storage/*` — проверками файловой системы, `server/db/*` — SQL-миграциями.

**Не изменено:** `app/recognition` (математика, вектора, группировка, назначение SAM), PostgreSQL-сессии, Caddy, текущая frontend/static, direct PUT/PATCH и full ZIP на zipstream-ng. `server/jobs.py` и `server/uploads.py` пока удерживают часть legacy бизнес-логики; миграция их оставшейся части должна быть отдельной тестируемой декомпозицией, не косметической заменой.

**Данные:** `Models/` отдельно от `PhotoSorter/`, файлы в постоянном bind mount, DB и HTTPS state — в Docker volumes. Образцы и их embedding cache не owned by batch. Результаты нового run имеют такой же manifest interface, а записываются во временный `.megaloc.building` каталог и атомарно публикуются в `outputs/<run_id>/megaloc/`.

**Конкурентность:** одна API-реплика (в upload используется process-local asyncio lock); Worker обеспечивает последовательную обработку в текущем Compose. `batch_operations` защищает реальные upload/ZIP потоки; delete-state блокирует новые операции, run enqueue и finish. Очистка запускается отдельным low-resource worker и ждёт прекращения jobs и live IO. Не масштабировать API/Worker до stage2 lease/queue audit.

Полные потоки перечислены в [PROJECT_MAP](../PROJECT_MAP.md), правила сохранности в [DATA_LIFECYCLE](DATA_LIFECYCLE.md).

## Stage 2 расширение

`server/main.py` остаётся сборщиком маршрутов. `server/api/routes/{thumbnails,references,originals,system}.py` содержит только HTTP-контракты; `server/services/{thumbnails,result_pages,disk_guard,temp_cleanup,thumbnail_gc}.py` — предметные операции; `server/db/repositories/{queue,pagination}.py` — SQL FIFO/keyset; `server/storage/thumbnail_cache.py` — кэш файлов без бизнес-логики.

`server/workers/thumbnail.py` выполняет обработку WebP вне upload HTTP, атомарно; отдельный Worker MegaLoc ограничен 1 running через session-level advisory leader lock плюс transaction gate. Новые `manifest.rows.jsonl` создаются параллельно старому неизменному manifest.json/CSV/ZIP, только для новых результатов. `app/logging/events.py` пишет ротационные JSONL и читает курсорно; Docker stdout тоже ротируется. `api/system` отображает измеренные времена API, не выдаёт гипотезы за факты.

**Ограничение:** stage2 написан и тестируется отдельно от пользовательского VPS; горизонтальное масштабирование API пока требует distributed upload locks. Целевая Vue UI не входит в этап 2.

## Stage 3 — отдельный Vue SPA слой

`frontend/static` и legacy `/` продолжают обслуживаться прежним backend. `frontend/src` построен на Vue3/Pinia/Vue Router/TypeScript; в runtime Python FastAPI отдаёт статический Vite `dist` по `/v3/`. Сборка Node24 выполняется только в Docker builder. Всё state сессии находится в httpOnly cookie, frontend хранит только theme и idempotent upload identity (не фото/пароли).

ФО/Образцы/Обработка/Результаты/Логи/Настройки имеют отдельные папки features; REST API клиенты и composables отделены от компонентов. Backend Stage3 добавляет небольшой `services/references.py` для SAM rename/delete/cache, расширяет list batch counters, tail log API и ручную очистку только ownerless thumbnail cache. Ядро `app/recognition/` не изменялось.
