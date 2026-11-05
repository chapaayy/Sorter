# Архитектура, этап 1

Исходное приложение было одним FastAPI `main.py` и modules `uploads/jobs/database`. После этапа 1 `server/main.py` выполняет только сборку приложения, middleware авторизации и lifecycle. `server/api/routes/*` имеют HTTP-контракты, `server/services/*` владеют batch/retention/cleanup/storage use cases, `server/storage/*` — проверками файловой системы, `server/db/*` — SQL-миграциями.

**Не изменено:** `app/recognition` (математика, вектора, группировка, назначение SAM), PostgreSQL-сессии, Caddy, текущая frontend/static, direct PUT/PATCH и full ZIP на zipstream-ng. `server/jobs.py` и `server/uploads.py` пока удерживают часть legacy бизнес-логики; миграция их оставшейся части должна быть отдельной тестируемой декомпозицией, не косметической заменой.

**Данные:** `Models/` отдельно от `PhotoSorter/`, файлы в постоянном bind mount, DB и HTTPS state — в Docker volumes. Образцы и их embedding cache не owned by batch. Результаты нового run имеют такой же manifest interface, а записываются во временный `.megaloc.building` каталог и атомарно публикуются в `outputs/<run_id>/megaloc/`.

**Конкурентность:** одна API-реплика (в upload используется process-local asyncio lock); Worker обеспечивает последовательную обработку в текущем Compose. `batch_operations` защищает реальные upload/ZIP потоки; delete-state блокирует новые операции, run enqueue и finish. Очистка запускается отдельным low-resource worker и ждёт прекращения jobs и live IO. Не масштабировать API/Worker до stage2 lease/queue audit.

Полные потоки перечислены в [PROJECT_MAP](../PROJECT_MAP.md), правила сохранности в [DATA_LIFECYCLE](DATA_LIFECYCLE.md).
