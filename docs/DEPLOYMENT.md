# Развёртывание и обновление PhotoSorter (beta)

Основная ветка — **`main`**. Сайт обслуживает **один** Vue SPA на `/`; прежних `/v3/` и `frontend/static` больше нет. Backend, Vue, Caddy и Docker Compose живут в одном репозитории.

## Требования

Linux x86-64, DNS домена на VPS и открытые TCP 80/443. На чистой Ubuntu/Debian `--deploy` от root устанавливает недостающие Docker Engine, Compose v2 и Python 3; на других дистрибутивах они должны быть установлены заранее. Рабочий Docker с Compose установщик не заменяет. Если уже установлен Docker из другого источника без Compose v2, сначала добавь совместимый плагин. По умолчанию установщик выбирает доступные CPU и оставляет один для системы, если CPU больше одного. Worker mem limit — 20 GiB, поэтому учитывай реальную RAM. Для больших фото нужны место на диске и стабильный канал.

## Установка на пустой сервер / пустое состояние

```bash
git clone --single-branch --branch main https://github.com/chapaayy/Sorter.git /opt/Sorter
cd /opt/Sorter
cp .env.example .env
nano .env
bash ./install.sh --deploy
```

`.env` содержит настоящий `DOMAIN` и заданный оператором `ADMIN_PASSWORD='…'` (16–256 символов). Он действует для входа под `admin` по `https://DOMAIN/` и не сохраняется в базе. При первой установке скрипт генерирует `.env.generated` только с `POSTGRES_PASSWORD`. Не публиковать и не коммитить оба файла. Модель можно скачать из интерфейса.

Сервисы Compose: `caddy`, `postgres`, `api`, `worker`, `thumbnail`, `cleanup`. Том PostgreSQL и TLS-тома Caddy постоянные, а `PhotoSorter/data` и `Models` — bind mounts. Новый `git clone` **не обнуляет** volumes существующего Compose с именем `outdoor-sorter`.

## Обновление работающего VPS

Перед обновлением получить проверенную внешнюю копию PostgreSQL, `PhotoSorter/data`, `Models`, `.env`, `.env.generated` и TLS volumes; см. [BACKUP_RESTORE](BACKUP_RESTORE.md), [ROLLBACK](ROLLBACK.md). Во время снимка все пишущие операции должны быть остановлены.

Если старый установщик хранил `ADMIN_PASSWORD` в `.env.generated`, задай его в `.env` до `--check`: можно перенести прежний пароль или выбрать новый. После успешного запуска Compose установщик удалит старую строку `ADMIN_PASSWORD` из `.env.generated`, не трогая пароль PostgreSQL. Миграция обнуляет старый хеш и соль админа без изменения ID пользователя. Для смены пароля отредактируй `.env` и запусти `bash ./install.sh --deploy`. Сессии админа закрываются при каждом старте API.

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
bash ./install.sh --deploy
docker compose --env-file .env --env-file .env.generated ps
```

`--check` **не** меняет файлы/пароли, не устанавливает пакеты и не запускает контейнеры. `--deploy` пересобирает и обновляет runtime, сохраняет существующие модели, файлы, PostgreSQL и сертификаты.

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
