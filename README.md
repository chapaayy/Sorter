# OUTDOOR PhotoSorter

**Бета · один сайт · основная ветка `main`.** Приватная система сортировки фотоотчётов наружной рекламы по конструкциям. Сейчас используется одна модель MegaLoc: она сначала группирует фотографии ФО (порог по умолчанию **0.50**), затем сопоставляет группы с общей библиотекой образцов SAM. Нейросетевая математика не меняется при переработке интерфейса.

## Одна актуальная версия

- Сайт: `https://<DOMAIN>/` — **Vue 3 + TypeScript**, без `/v3/` и параллельного старого интерфейса.
- Страницы: `/fo`, `/references`, `/processing`, `/results`, `/logs`, `/settings`. Вход: `/login`.
- API: `/api/*` на том же домене. Данные и авторизация остаются на сервере.
- Код развивается в **`main`**; отдельные исторические ветки не являются версиями для установки.
- `PhotoSorter/frontend/static/` удалён. Единственный frontend — `PhotoSorter/frontend/src/`; результат сборки находится в игнорируемом `dist/`.

## Установка на новый пустой сервер

Linux x86-64, Docker Engine + Compose v2, Python 3, собственный домен с DNS на сервер, доступные TCP 80/443. Целевая конфигурация: 8 vCPU (доступность CPU IDs 0–6), около 24 ГБ RAM и 200 ГБ диска. Указанные CPU — настройки, а не гарантия скорости обработки.

```bash
git clone --branch main --single-branch https://github.com/chapaayy/Sorter.git
cd Sorter
cp .env.example .env
nano .env            # DOMAIN=ваш-настоящий-домен
bash ./install.sh --deploy
docker compose --env-file .env --env-file .env.generated ps
```

**Примечание:** на пустой установке `--deploy` сгенерирует секреты; `--check` предназначен для проверки уже настроенного окружения. Логин `admin`, пароль сохранён в приватном `.env.generated`, который нельзя удалять или добавлять в Git. Модель/веса можно загрузить из веб-интерфейса.

В результате поднимаются `caddy` (HTTPS), `postgres`, `api`, `worker` (MegaLoc), `thumbnail` (WebP) и `cleanup` (служебная очистка). Снаружи публикуются только 80/443.

### Обновление ранее установленного PhotoSorter

`git pull` и новая папка `git clone` **не сбрасывают существующую базу**. Compose использует постоянное имя `outdoor-sorter` и Docker volumes. Перед обновлением проверить `git status`, `./install.sh --check` и согласованную копию PostgreSQL + `PhotoSorter/data` + `Models` + `.env.generated` (внешнее защищённое хранилище, тест восстановления). После проверки бэкапа обновление запускают:

```bash
git fetch origin main
git switch main
git pull --ff-only origin main
PHOTOSORTER_APPROVE_UPGRADE=VERIFIED_BACKUP_AND_ROLLBACK bash ./install.sh --deploy
```

Если ранее сервер был на detached commit, сперва проверить локальные изменения: `git switch main` может требовать разрешения конфликтов. Токен `PHOTOSORTER_APPROVE_UPGRADE` применять **только после действительно проверенного бэкапа**, не ради обхода защиты.

**Полный бета-сброс** (включая удаление базы, фотографий, SAM и исторических результатов) — отдельная операция, не часть `git pull` или `install.sh`. Инструкция: [SINGLE_SITE_INSTALL](docs/SINGLE_SITE_INSTALL.md). Не использовать `docker compose down -v` как команду обновления.

## Работа

1. **Образцы:** создать библиотеку `SAM-xxxx` из папок с фотографиями конструкций.
2. **ФО:** загрузить папку фотоотчёта, дождаться передачи оригиналов и формирования миниатюр.
3. **Обработка:** выбрать партию, MegaLoc и порог, затем запустить очередь. Один MegaLoc Worker выполняет одно задание за раз.
4. **Результаты:** проверить назначенные SAM и неопределённые фотографии; скачать полный ZIP. Отдельное подтверждение сохранения ZIP запускает срок хранения партии — два календарных месяца UTC, предупреждение за семь дней.
5. **Логи и настройки:** следить за состоянием фоновых служб, диска, логами обработки и галереями.

## Где хранятся данные

| Путь / Docker volume | Назначение |
|---|---|
| `Models/models/` | Веса моделей; вне Git |
| `Models/cache/` | Кэш загрузчиков и библиотек; вне Git |
| `PhotoSorter/data/references/` | Постоянные образцы SAM |
| `PhotoSorter/data/uploads/` | Оригиналы партий ФО |
| `PhotoSorter/data/runs/`, `outputs/` | История обработок и результаты |
| `PhotoSorter/data/cache/` | Только служебные кэши, в том числе WebP и embeddings образцов |
| `outdoor-sorter_postgres_data` | PostgreSQL: пользователи, партии, задания, очереди |
| `outdoor-sorter_caddy_data`, `caddy_config` | Сертификаты HTTPS и состояние Caddy |

**Файлы в `Models/` и `PhotoSorter/data/` не являются частью репозитория.** Изменение ветки не очищает их.

## Разработка и тестирование

```bash
# Frontend — Node.js 24
cd PhotoSorter/frontend
npm ci
npm run build
npm run test
npx playwright install chromium webkit
npm run test:e2e

# Backend — Python 3.11 + PostgreSQL 17 в изолированной среде
PYTHONPATH=PhotoSorter/backend python -m pytest -q PhotoSorter/backend/tests
```

Единый workflow `.github/workflows/ci.yml` на `main` проверяет Python/SQL/Compose/Caddy, backend, PostgreSQL dump→restore, Vue/Playwright и полный изолированный Docker startup. Синтетические тесты **не доказывают** качество распознавания на реальных фотографиях.

Подробности: [архитектура](PROJECT_MAP.md), [индекс файлов](FILE_INDEX.md), [правила разработки](AGENTS.md), [API](docs/API.md), [операции](docs/OPERATIONS.md), [бэкапы](docs/BACKUP_RESTORE.md), [тестирование](docs/TESTING.md).
