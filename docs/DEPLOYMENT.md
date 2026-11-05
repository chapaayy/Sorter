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

## Stage 3 — Vue rollout только на изолированном staging

1. Убедиться, что текущий commit — отдельная ветка `stage3/vue-frontend`, а не действующий `vps/docker-rebuild`. У Stage 3 есть зависимость от Stage 2 (preview, galleries, logs, queues).
2. Не менять боевой VPS. На **изолированном** 8-vCPU стенде проверить CPU affinity, PostgreSQL 17, mount `PhotoSorter/data`, `Models/models` и `Models/cache`.
3. Dockerfile multi-stage: сборка `node:24-alpine` `npm ci` + `npm run build`, только `dist/` переносится в Python 3.11 final image; Node не присутствует в backend/runtime.
4. Один Vue-интерфейс на `/` и deep links `/fo`, `/references`, `/processing`, `/results`, `/logs`, `/settings`. Протестировать cookie/login, sidebar, FO uploads, SAM gallery/rename, queued runs, full ZIP, explicit confirmation и settings; старые `/v3/` и `/static/*` отвечают 404.
5. Отдельно проверить CSP/headers, HTTPS/SameSite cookies, iPhone Safari/iOS, 360px responsive, tab/focus/Escape, browser cache invalidation, исходные photos and SAM, disk quota.
6. По явному запросу владельца новый Vue теперь единственный UI в коде. Это не разрешение стирать постоянные фото/Models/PostgreSQL; `docker compose down -v` не выполнять при обычном обновлении.

## Stage 4: fail-closed update safeguards

Инсталлятор теперь имеет `./install.sh --check` (**без новых паролей, без chown, без Docker up**) и `./install.sh --deploy`. Если Docker volume `outdoor-sorter_postgres_data` уже существует, а `.env.generated` утрачена, скрипт **останавливается** и требует restore исходных credentials: новый пароль вместо прежнего создать нельзя.

Для обновления существующего инстанса после **реально проверенного** offsite backup/restore требуется установка `PHOTOSORTER_APPROVE_UPGRADE=VERIFIED_BACKUP_AND_ROLLBACK` оператором, иначе никаких новых контейнеров/изменений данных. При обновлении отключён рекурсивный chown моделей и фото. CPUSET проверяется по фактически разрешённым CPU IDs ещё до Docker startup. Административные пароли не выводятся в stdout.

Это **не автоматическое разрешение production rollout**: до реального VPS обязательно пройти [STAGE4_ACCEPTANCE](STAGE4_ACCEPTANCE.md) и отдельно получить разрешение владельца. Миграция `0007_service_heartbeat.sql` аддитивная; все предыдущие таблицы остаются.
