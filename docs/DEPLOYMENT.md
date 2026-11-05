# Развёртывание и эксплуатация — этап 1 (staging only)

1. **Production VPS не трогать без отдельного разрешения.** Код `stage1/batch-lifecycle-hardlinks` предназначен для тестового стенда. Проверьте `git rev-parse HEAD`, `docker compose config`, mounts/UID перед первым запуском.
2. Перед любой миграцией реальных данных: консистентный backup PostgreSQL + `PhotoSorter/data` + `Models` + `.env.generated`, восстановить на изолированном стенде. См. [BACKUP_RESTORE](BACKUP_RESTORE.md).
3. `compose.yaml` теперь содержит `cleanup` и `thumbnail` с CPU/memory limit; вместе с `api` выполняет `wait_and_initialize()`, версионируемую миграцию. По умолчанию фоновая очистка **может** удалять подтверждённые по новому API партии после срока. Не разворачивать её на рабочем сервере без полного испытания.
4. Сохранить bind mounts: `./PhotoSorter/data:/workspace/PhotoSorter/data`, `./Models:/workspace/Models`; `postgres_data` volume без изменения; Caddy TLS volumes без изменения.
5. Проверить `docker compose config --quiet`, `docker compose up -d --build` **только на staging**, затем `/api/health`, авторизацию, legacy PUT/PATCH, SAM, MegaLoc, ZIP, cleanup.
6. `docker compose logs -f api worker cleanup` для диагностики. Не использовать `docker compose down -v` / `docker system prune --volumes` / `rm -rf PhotoSorter/data`.
7. Нагрузочные и реальные regression tests 189/1315 ФО, disk/CPU/OpenSSL/TLS и offsite backups проверяются отдельно перед production.

Оригинальная инструкция развертывания: [PhotoSorter/docs/DEPLOYMENT.md](../PhotoSorter/docs/DEPLOYMENT.md). План отката: [ROLLBACK.md](ROLLBACK.md).

## Дополнительные условия stage2

Новый `thumbnail` контейнер работает с CPU=0.35 и RAM=512MiB. Worker MegaLoc на **8-vCPU staging** настроен на cpus=7, cpuset `0-6`, `PHOTOSORTER_CPU_THREADS=7`. Перед test `docker compose up` обязательно проверить допустимый CPU affinity текущего хоста; для 4-vCPU стенда нужна явная переустановка `PHOTOSORTER_WORKER_CPUSET` и CPU quota. Не менять CPU/Caddy на рабочем VPS без согласованного A/B.

Docker `json-file` logs max-size 10m/max-file 3, data/cache/thumbnails shared mount, PG additive migrations 0003–0006. Учесть DB row/index backups, restore preview tasks and cache state. `docker compose config --quiet` проверяется автоматически; runtime `docker compose up --build` **в этой беседе не запускался**.
