# Миграционные заметки этапа 1

**Исходный HEAD:** `8c82924b9077b4374fa223f777f3df5453f721e4` (ветка `vps/docker-rebuild`, 05.11.2026). Не менять эту ветку.

**Исходная схема:** `users`, `sessions`, `batches(id,created_at)`, `uploads`, `jobs`, `reference_cache`. До миграции `batches` не имела display_name, expiry и статуса удаления. Старые результаты `outputs/<run_id>` физически копировались. Existing `zipstream-ng` делает общий ZIP без временного файла. Кэш MegaLoc только для SAM refs, ФО инференс — каждый запуск.

**Новая миграция:** `server/db/migrations/0001_batch_lifecycle.sql`, `schema_migrations(version,applied_at)` и версия скрипта. Аддитивные `ALTER TABLE ADD COLUMN IF NOT EXISTS`, индекс по due dates/jobs, таблицы операций/confirmations/cleanup. Для старых партий без имени — `ФО DD.MM.YYYY HH:MM` по историческому `created_at` в UTC. Существующие `uploads.batch_id`, `jobs.batch_id` сохраняются, не нужен массовый обход/перенос файлов. Старые runs и manifests продолжают читаться.

**Новые outputs:** только свежие обработки создают Hard Links там же, где прежние копии; расположение `data/outputs/<run_id>/megaloc/<SAM>` и format manifest/ZIP сохранены. Временные каталоги `.megaloc.building` не являются завершёнными результатами; при исключении очищаются. Crash до финализации может оставить staging, который не публикуется и может быть удалён только после проверки отсутствия активного run. Массовая дедупликация старых файлов запрещена.

**Выполнение только на изолированном staging:** `pg_dump` + полный согласованный снимок файлов; проверить restore, запустить контейнеры с новым кодом/миграцией; проверить старые партии/ZIP, новый hardlink run, DELETE owned batch и restoration. После одобрения пользователя отдельный production rollout. Нельзя пересоздать DB или очистить volume ради миграции.

**Rollback:** только совместимый кодовый откат; новые столбцы/таблицы в DB безопасно оставить, чтобы не потерять подтверждения/cleanup logs. Откат к старому приложению может потерять семантику новых retained batches, поэтому остановить cleanup и проверить записи; см. [ROLLBACK](ROLLBACK.md).

Дополнительная `0002_batch_upload_state.sql` безопасно вычисляет `upload_state` для уже существующих партий по текущим uploads/jobs; после миграции runtime держит поле согласованным при create/finalize/delete/первом запуске.

## Stage 2 — добавленные migration scripts

- `0003_thumbnails_queue.sql`: `uploads.updated_at` + очередь preview (`thumbnail_tasks` с FK CASCADE), claim/lease/retry/state indexes, backfill старых **finalized** ФО и Образцов без изменения исходников.
- `0004_megaloc_queue.sql`: `jobs.started_at/finished_at`, FIFO/active indexes. Существующие статусы/результаты не меняются.
- `0005_result_pages.sql`: индекс finalized FO `uploads.target_path` для галерей по ID; manifests untouched.
- `0006_unfinished_age.sql`: индекс только старых незавершённых uploads для безопасного 30-day TTL.
- Новый `manifest.rows.jsonl` создаётся **для новых запусков** параллельно прежним JSON/CSV; для старых результатов предусмотрен fallback. Никакие старые копии outputs/веса не мигрируются.

Все миграции аддитивные, применяются по версии `schema_migrations`. Старт `thumbnail` и `cleanup` после backup/restore только на отдельном staging. Не запускать SQL вручную на боевом VPS.

## Этап 3: Vue и API без новой схемы БД

Stage 3 не добавляет таблицы или миграционные SQL. Он использует уже существующие Stage1/2 batches, uploads, jobs, thumbnail_tasks, reference_cache, run logs; дополнительные HTTP handlers для SAM, cursor-tail и cache cleanup находятся в сервисах/роутерах. Production-база не изменялась. Статический frontend build не должен перезаписывать `frontend/static/`, `data/` или `Models/`.

## Stage 4 — additive heartbeat

`0007_service_heartbeat.sql` создаёт `service_heartbeats(service PRIMARY KEY, instance_id UUID, seen_at TIMESTAMPTZ)` и индекс по seen_at. Не удаляет и не изменяет старые rows, credentials, uploads, runs, результирующие manifests. Миграция идемпотентна, применяется в той же транзакции что предыдущие миграции. Парсер `migration_runner.py` теперь пропускает полные строки `-- SQL comment` до разделения на `;`, чтобы пунктуация комментариев не исполнялась как SQL. Как прежде, процедурные SQL-блоки не поддерживаются.
