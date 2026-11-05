# Safe rollback: code and additive schema

Не выполнять rollback на живом VPS без явного одобрения и проверенной резервной копии. Исходный commit `8c82924b9077b4374fa223f777f3df5453f721e4` в `vps/docker-rebuild`.

**Тестовый сценарий отката:** прекратить новые операции и дождаться завершения/отмены старых ZIP/run/cleanup. Сохранить DB и persistent FS snapshot, проверить версии `schema_migrations` и наличие unfinished `cleanup_tasks`. Переключить тестовый код/контейнеры на исходный commit, **оставив data/Models/postgres_data без удаления**. Старые приложения могут игнорировать новые столбцы/таблицы, но не знают retention tasks: остановить cleanup при rollback. Проверить login, старые uploads/ZIP и читаемость completed manifests.

**Не делать `DROP TABLE` или `DROP COLUMN` автоматически.** Stage1 миграция аддитивна; откат SQL с удалением данных запрещён без анализа и снимка. Для отмены опасной auto-retention прежде всего остановить именно `cleanup` контейнер в staging, не удаляя файлы/DB.

После разницы форматов при смене кода не продолжать необратимые file/delete операции; восстановление до консистентного состояния — только из протестированного backup. `docker compose down -v` запрещён.
