# Развёртывание и обновление PhotoSorter (beta)

Стабильная основа — **`main`**. Для экспериментальной установки поиска экранов использовать **`feature/ad-recognition`** только на новом VPS. Сайт обслуживает **один** Vue SPA на `/`; прежних `/v3/` и `frontend/static` больше нет. Backend, Vue, Caddy и Docker Compose живут в одном репозитории.

## Требования

Linux x86-64, Docker Engine + Compose v2, Python 3, DNS домена на VPS и открытые 80/443. По умолчанию `PHOTOSORTER_WORKER_CPUSET=0-6` и `PHOTOSORTER_WORKER_CPUS=7`; на сервере с менее чем семью доступными CPU ID установить допустимый cpuset в shell или `.env` до проверки. Worker mem limit — 20GiB, поэтому учитывать реальную RAM. Для больших фото нужны место на диске, CPU PyTorch и стабильный канал.

## Установка на пустой сервер / пустое состояние

```bash
git clone --single-branch --branch main https://github.com/chapaayy/Sorter.git
cd Sorter
cp .env.example .env
nano .env
bash ./install.sh --deploy
docker compose --env-file .env --env-file .env.generated ps
```

`.env` содержит `DOMAIN=...` с настоящим доменом. При первой установке скрипт генерирует `.env.generated` с `ADMIN_PASSWORD` и `POSTGRES_PASSWORD`. Не публиковать, не коммитить, сохранить отдельно. Сайт: `https://DOMAIN/`. Логин: `admin`. Модель может быть скачана из интерфейса.

Сервисы Compose: `caddy`, `postgres`, `api`, `worker`, `thumbnail`, `cleanup`. Том PostgreSQL и TLS-тома Caddy постоянные, а `PhotoSorter/data` и `Models` — bind mounts. Новый `git clone` **не обнуляет** volumes существующего Compose с именем `outdoor-sorter`.

## Обновление работающего VPS

Перед обновлением получить проверенную внешнюю копию PostgreSQL, `PhotoSorter/data`, `Models`, `.env`, `.env.generated` и TLS volumes; см. [BACKUP_RESTORE](BACKUP_RESTORE.md), [ROLLBACK](ROLLBACK.md). Во время снимка все пишущие операции должны быть остановлены.

На VPS со старой веткой/отсоединённым HEAD сначала проверить `git status --short`. Не перетирать локальные изменения. Затем:

```bash
cd /root/Sorter
git fetch origin main:refs/remotes/origin/main
git switch main || git switch -c main --track origin/main
git merge --ff-only origin/main
bash ./install.sh --check
```

После успешного preflight, snapshot и теста восстановления:

```bash
PHOTOSORTER_APPROVE_UPGRADE=VERIFIED_BACKUP_AND_ROLLBACK bash ./install.sh --deploy
docker compose --env-file .env --env-file .env.generated ps
```

`--check` **не** меняет файлы/пароли и не запускает контейнеры. `--deploy` пересобирает и обновляет runtime, сохраняет существующие модели, файлы, PostgreSQL и сертификаты. Токен одобрения не использовать, если резервная копия действительно не проверена.

Проверить `/api/health`, вход, `/`, `/fo`, `/references`, `/processing`, просмотр фото, историю runs, ZIP, состояния трех background workers, HTTPS и ошибки. Любые данные настоящей партии удалять только после осознанного выбора.

## Бета-сброс данных — отдельное действие

Если все временные SAM, ФО и история не нужны, это **полный сброс состояния**, а не обычное обновление: остановка всех сервисов, проверенная независимая копия, явно указанный список каталогов и PostgreSQL volume, повторная первичная установка с новыми секретами. Изменение кода `main` не должно делать это неявно. См. [SINGLE_SITE_INSTALL](SINGLE_SITE_INSTALL.md).

Никогда не применять `docker compose down -v`, `docker system prune --volumes`, `rm -rf PhotoSorter/data` как «быстрый апдейт» без отдельного подтверждения полного удаления. Миграции БД от 0001 до 0007 необходимы свежей установке, это не хлам и не отдельные версии сайта.

## Проверки и диагностика

```bash
docker compose --env-file .env --env-file .env.generated ps
docker compose --env-file .env --env-file .env.generated logs --tail=100 api worker thumbnail cleanup
df -h /
```

Единый GitHub CI — [`.github/workflows/ci.yml`](../.github/workflows/ci.yml); результаты CI не заменяют реальный приемочный набор ФО.

## Чистый экспериментальный VPS (feature/ad-recognition)

```bash
git clone --single-branch --branch feature/ad-recognition https://github.com/chapaayy/Sorter.git
cd Sorter
cp .env.example .env
nano .env
bash ./install.sh --check
bash ./install.sh --deploy
```

Первый `--check` может отметить отсутствие `.env.generated`, пока `--deploy` не создаст секреты. Проверить доступные CPU ID, RAM (лимит Worker), свободное место, `docker compose config` и логи. Не выполнять `down -v` и не чистить тома при обновлении. Дальнейшие обновления с `git pull --ff-only origin feature/ad-recognition`, не переключать эксперимент на `main` без команды владельца.


## XFeat на CPU (ручной этап 2 после установки ветки)

```bash
docker compose exec api python -m app.screen_detection.cli --install
docker compose exec worker python -m app.screen_detection.cli --verify
docker compose exec worker python -m app.screen_detection.cli --run-id RUN_ID --limit 20
```

API подключён к внешней Docker-сети, а Worker — только к private, поэтому
скачивание модели запускается в API, а inference — в Worker.
`--install` проверяет точные Git blob контрольные суммы официальных
исходников/весов, не перезаписывает корректные файлы. Если VPS не имеет
доступа, перенести `Models/models/xfeat/xfeat.pt` и
`Models/cache/xfeat/official/modules/*.py` с ПК, сохранив структуру;
проверить `--verify` до запуска. Не добавлять бинарные веса в Git.
ФО после MegaLoc анализируются отдельно, результат в outputs партии.
Никаких команд `docker compose down -v` для такого обновления не требуется.
