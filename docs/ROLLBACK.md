# Safe rollback: code and additive schema

Не выполнять rollback на живом VPS без явного одобрения и проверенной резервной копии. Исходный commit `8c82924b9077b4374fa223f777f3df5453f721e4` в `vps/docker-rebuild`.

**Тестовый сценарий отката:** прекратить новые операции и дождаться завершения/отмены старых ZIP/run/cleanup. Сохранить DB и persistent FS snapshot, проверить версии `schema_migrations` и наличие unfinished `cleanup_tasks`. Переключить тестовый код/контейнеры на исходный commit, **оставив data/Models/postgres_data без удаления**. Старые приложения могут игнорировать новые столбцы/таблицы, но не знают retention tasks: остановить cleanup при rollback. Проверить login, старые uploads/ZIP и читаемость completed manifests.

**Не делать `DROP TABLE` или `DROP COLUMN` автоматически.** Stage1 миграция аддитивна; откат SQL с удалением данных запрещён без анализа и снимка. Для отмены опасной auto-retention прежде всего остановить именно `cleanup` контейнер в staging, не удаляя файлы/DB.

После разницы форматов при смене кода не продолжать необратимые file/delete операции; восстановление до консистентного состояния — только из протестированного backup. `docker compose down -v` запрещён.

## Откат stage2 отдельно от stage1

1. На **тестовом** стенде прекратить новые uploads и queued jobs, остановить `thumbnail`, `cleanup`, `worker`, дождаться окончания ZIP и сделать согласованный backup PG+data.
2. Вернуть код на коммит stage1 `9eb865d321a67890e414da4d17643ce1d046f51b` (или staging deployment tag) без удаления `Models/`, `PhotoSorter/data/` или PostgreSQL/Caddy Docker volumes.
3. Аддитивные `thumbnail_tasks`, `uploads.updated_at`, новые индексы, jobs timestamps безопасно **оставить в PostgreSQL**, не выполнять DROP. Старый код игнорирует новые колонки; очередь будущих queued jobs нужно учесть перед откатом, не запускать параллельный model worker.
4. Проверить старые auth/resumable uploads, manifest/ZIP, чтение output, отсутствие cleanup while rollback. Все реальные данные/снимки — только с отдельным разрешением владельца.

## Stage 3 UI rollback

Самый безопасный откат UI — **перестать открывать `/v3/`**, продолжить работу на существующем `/`. Ни старый `frontend/static`, ни работающие upload/ZIP API для этого не нужно менять. Если нужно откатить Docker образ, использовать stage2 commit `9ecb75194a9e388ba8e0391fa6d6e56529dea0c0` **на staging**, сохранив volume PostgreSQL и data.

Новые rename/delete SAM требуют аккуратной приёмки: исторические результаты могут ссылаться на старые пути Образцов. Не проводить переименование реальных SAM до проверки старых manifests; при неудачном тесте восстановить из согласованного backup. Не запускать full-production rollback только ради смены темы.
