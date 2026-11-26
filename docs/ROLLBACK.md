# Storage V2 — восстановление после неудачного обновления

Не переключать branch, не применять git reset --hard и не удалять storage при ошибке. Branch pin остаётся feature/storage-architecture-v2. Обновлятор сохраняет текущий/предыдущий помеченный образ и защищённый backup DB/config; при сбое после переключения сохраняет marker и сообщает recovery_required. Это намеренно не автоматический rollback данных.

1. Не начинать повторное обновление/установку поверх активного перехода. Проверить root-only статус updater, journal, free space, maintenance marker, действующую и целевую ревизии, состояние всех шести сервисов, heartbeat и HTTPS.
2. Сохранить диагностические сведения без секретов. Защитить существующий backup. До опасных действий согласовать восстановление с владельцем.
3. Полный согласованный снимок и проверка restore на изолированном стенде описаны в [BACKUP_RESTORE](BACKUP_RESTORE.md). Только проверенные schema/data compatibility и конкретный образ/SHA позволяют планировать откат приложения. Локальный образ/PG dump обновлятора не заменяют независимый бэкап оригиналов, модели и Caddy TLS.
4. Никакого автоматического overwrite рабочего PGDATA или старого VPS. При повреждении базы/файлов восстановление на отдельном стенде, затем отдельная согласованная процедура переключения.
5. После восстановления проверять login/permissions, HTTPS, native health PostgreSQL/API, свежие heartbeat MegaLoc/thumbnail/cleanup, hashes of media and model, reference cache, results/ZIP и registry. Зафиксировать revision and measured evidence.

Никаких global Docker prune, удаления volumes/WAL/сертификатов или ручного удаления неизвестных файлов. [Установка](DEPLOYMENT.md) · [Эксплуатация](OPERATIONS.md).
