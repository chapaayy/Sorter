# Безопасное развёртывание, тестирование и откат

**Это руководство для каждого следующего обновления `main`, а не автоматическое разрешение удалять действующие данные.** На бета-VPS уже развёрнуты тестовые версии; любое следующее изменение требует отдельной проверки и сохранения резервной копии.

## 1. Подготовка отдельного стенда

1. Отдельный сервер или docker host, отдельные volume и домен тестового контура, не делать сетевой reverse proxy к действующей PostgreSQL и не монтировать действующие `PhotoSorter/data` / `Models`.
2. Проверить аппаратные CPU IDs в cgroup, минимум доступные 7 logical CPU для базового `cpuset=0-6`; иначе установить `PHOTOSORTER_WORKER_CPUSET` на реально доступный диапазон. Cpuset **не резервирует** физическое ядро для API.
3. Получить код строго из отдельной main commit, доступные weights (с подписью), копию тестовых 189/1315 фото/Образцов **только с разрешения**.
4. На staging выполнить `./install.sh --check` (только чтение). Если секреты/Compose/CPU не подходят — исправить до запуска.
5. На пустом staging настроить .env и установить `./install.sh --deploy`. Не направлять DNS на боевой VPS. Для уже существующего volume обновление требует отдельного `PHOTOSORTER_APPROVE_UPGRADE=VERIFIED_BACKUP_AND_ROLLBACK`.
6. Проверить `docker compose ps`, `GET /api/health`, авторизованный `GET /api/system/status` и heartbeat `services.megaloc/thumbnail/cleanup`. Проверить единый Vue на `/`, deep links `/fo`/`/references`, assets `/assets/*`, старые `/v3/` и `/static/*` должны отвечать 404. Пустая очередь не является доказательством работы Worker.

## 2. Согласованный архив и восстановление

**Перед снимком должна быть остановлена запись**: ни uploads/finalize/jobs/export/cleanup/thumbnail, ни обновление reference-cache. Не считать `pg_dump` согласованным со свободно меняющимися файлами.

```bash
# ЗАПУСКАТЬ только на согласованном изолированном стенде и с его DATABASE_URL.
# Строку подключения читайте из защищённого окружения/файла, не вставляйте пароль в shell history.
python PhotoSorter/tools/maintenance/snapshot.py capture \
  --root /path/to/staging-repo \
  --destination /external/offsite-mount/photosorter-snapshot-YYYYMMDD \
  --database-url "$DATABASE_URL" \
  --ack-writers-stopped
python PhotoSorter/tools/maintenance/snapshot.py verify \
  --archive /external/offsite-mount/photosorter-snapshot-YYYYMMDD

# Для restore-test нужен отдельный существующий ПУСТОЙ PostgreSQL DB,
# название sorter_restore_*, и НОВЫЙ каталог со специальной меткой родителя.
mkdir -p /isolated-restore
printf 'STAGING_ONLY\n' > /isolated-restore/.photosorter-staging-only
python PhotoSorter/tools/maintenance/snapshot.py restore-test \
  --archive /external/offsite-mount/photosorter-snapshot-YYYYMMDD \
  --destination /isolated-restore/project \
  --database-url "$DISPOSABLE_RESTORE_DATABASE_URL" \
  --confirm-staging
```

Содержимое архива: `PhotoSorter/data`, `Models/models`, `Models/cache`, `.env`, `.env.generated`, `compose.yaml`, `Caddyfile` и `pg_dump`. **В архиве есть пароли и реальные фото — хранить только в зашифрованном внешнем хранилище с 0600/0700**. Caddy volume с сертификатами и SSL private keys находится в отдельном Docker volume и **не входит** в snapshot.py; его резервирование/восстановление выполняется отдельно в соответствии с политикой хостера. Нельзя удалять Caddy volume автоматически. `down -v` запрещён.

## 3. Проверка модели, реальной производительности и UI

```bash
python PhotoSorter/tools/maintenance/compare_baseline.py \
  --baseline-manifest /verified/189/manifest.json \
  --candidate-manifest /staging/189/manifest.json \
  --baseline-zip /verified/189/results.zip \
  --candidate-zip /staging/189/results.zip
python PhotoSorter/tools/maintenance/staging_probe.py \
  --url http://127.0.0.1:8000 --count 200 --concurrency 4 \
  --output /tmp/stage4-health-baseline.json
```

Если одинаковых реальных материалов нет — сравнение остаётся блокером. Запуск MegaLoc проводить только на staging и с контролем модели; сохранить exit code/отчёт сравнения. Сопоставить старый 8/8 и новый 7/7 режимы по 3–5 прогонам. Проверить на физическом iPhone и десктопах.

## 4. Production rollout — ТОЛЬКО после явно полученного разрешения

После зафиксированных approval+offsite backup/restore:
1. Read-only audit `./install.sh --check`, snapshot и подтверждение целостности. Обязательно сохранить исходный git SHA, `.env.generated` и Docker volume IDs.
2. На выделенном окне обслуживания остановить пишущие операции согласованно. Сначала additive DB migrations, затем сервисы и новый UI. Запускать только зафиксированный проверенный коммит, не latest main.
3. Единственный UI — Vue на `/`; разделы имеют чистые адреса (`/fo`, `/references`, `/processing`, `/results`, `/logs`, `/settings`). Legacy UI удалён из release-кода; откат возможен на сохранённый прежний commit/image. Не удалять реальные данные и Docker volumes.
4. Smoke: login, старые batches/runs/ZIP, новый upload на тестовой партии, preview, Queue, log, retention без реального удаления, состояние Worker/DB/TLS. Проверить свободное место и журналы.
5. Мониторинг p95/error rate/disk/worker heartbeat, сравнение с staging, откат при ухудшении.

### Rollback

Если несоответствие, прекратить новые операции, не запускать старый и новый inference Worker параллельно. Вернуть **code image из предыдущего SHA**, оставить аддитивные SQL таблицы и volume; DB/filesystem возвращать из полного snapshot только при доказанной несогласованности и в согласованном maintenance window. Никаких `DROP`, `rm -rf PhotoSorter/data`, `docker compose down -v`. См. `docs/ROLLBACK.md`.
