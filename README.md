# OUTDOOR PhotoSorter — VPS / MegaLoc (этапы 1–4, Stage 4 pending production acceptance)

Приватный фотоотчёт рекламных конструкций. MegaLoc сначала группирует **только ФО** (порог по умолчанию 0.50), затем сопоставляет группы с общей библиотекой SAM. Нейронная математика, постоянные модели и кэш эталонов в этапе 1 не изменялись.

## Статус веток и безопасность

- Стабильная исходная ветка: `vps/docker-rebuild`.
- Разработка этапа 1: `stage1/batch-lifecycle-hardlinks` (отдельная ветка, не production).
- Изменения этапа 1 — новая схема и фоновые операции удаления; **не запускать на действующем VPS без резервной копии, проверки восстановления и явного разрешения**.
- Никаких удалений, миграций и развёртываний на VPS в ходе работы над веткой не выполнялось.
- **Этап 2:** `stage2/performance-thumbnails-queue`, отдельная ветка от этапа 1. **Этап 3:** `stage3/vue-frontend`, отдельная ветка от этапа 2 (PR будет отдельно). Этап 4 (production validation) не реализован.

## Этап 1: какие серверные функции добавлены

- Версионируемые **аддитивные SQL-миграции**: существующие таблицы, загрузки, пользователи, сессии и работы сохраняются. Старые партии получают отображаемое имя.
- API `/api/batches`: список, создание именованной партии, детали, переименование, метаданные фото, безопасное удаление одного ФО **только до первого запуска**, асинхронный запрос полного удаления партии.
- Все результаты **новых запусков** публикуются атомарно из временной директории и используют проверенные Hard Links; при EXDEV/неподдерживаемой ФС — безопасный fallback на копирование. Старые физические копии не мигрируются.
- `GET /api/download/{run_id}` продолжает выдавать ZIP потоком, теперь со счётчиком активных операций, чтобы очистка ожидала завершения потока. `?sam=` сохранён.
- `POST /api/batches/{id}/downloads/confirm`: **явное** подтверждение сохранённого общего архива; срок 2 календарных месяца UTC. Новый run сбрасывает подтверждение. `POST .../retention/extend` продлевает срок.
- Фоновый контейнер `cleanup` сканирует подтверждённые партии, проверяет активные задания/передачи и удаляет **только привязанные к партии** uploads, outputs, runs и временные .part. Не трогает `Models/`, `references/` и другие партии. Для удаления есть task/status, безопасный повтор после сбоя.
- `GET /api/storage/usage` отдаёт реальную ёмкость тома данных и оценку физического объёма файлов с дедупликацией inode. Размер PostgreSQL (отдельный volume) в категории не включён.

**Интерфейс остаётся прежним до этапа 3.** Старые PUT/PATCH, авторизация и потоковый ZIP сохраняются.

## Этап 2 — серверная платформа

- Финализация upload записывает `thumbnail_tasks` в PostgreSQL **без ожидания** конвертации. Низкоприоритетный `thumbnail` Worker создаёт content-addressed WebP 480px quality 78, EXIF/ICC, защищён от больших изображений, восстанавливает просроченные задачи и ограничивает число попыток.
- Пагинация и новые API: `/api/batches/{id}/gallery`, `/api/references/{sam}/photos`, `/api/results/{run_id}/photos`, `/api/thumbnails/{photo_id}`, `/api/photos/{photo_id}/original`; оригиналы только для viewer, старые полные results API сохранены.
- MegaLoc имеет PostgreSQL FIFO до 20 ожидающих, 1 running на лидера, DB-ограничитель, `queue_position`, отмену и `interrupted` при рестарте. Распознавание, grouping/math и SAM не менялись.
- Docker `json-file` лог-ротация 10m×3 на контейнер; run JSONL 4MiB×5 и общий бюджет ~512MiB с фильтрами и cursor пагинацией.
- Контроль места по `statvfs` и системный резерв (HTTP 507 на **новые** записи), удаление только устаревших незаконченных `.part` (30 дней/нет активных операций), reaper превью только без владельцев.
- Предварительная **8-vCPU staging** настройка Worker 7 threads, cpuset 0–6, отдельный thumbnail CPU quota 0.35. Никаких обещаний ускорения без A/B на разрешённом тестовом VPS.
- Мониторинг `/api/system/status`, расширенный `/api/storage/usage`; замер p95 тестового API: `python PhotoSorter/tools/benchmark_api.py --url http://127.0.0.1:8000/api/health --count 100`.

**На живой VPS ветка не развёрнута;** отсутствуют разрешение на production, backup/restore и real 1315-ФО benchmark. Подробности: [PERFORMANCE](docs/PERFORMANCE.md), [OPERATIONS](docs/OPERATIONS.md).


## Запуск текущей стабильной версии (без переключения на ветку этапа 1)

Требования: Linux x86-64, Docker Engine + Compose v2, домен с доступными портами 80/443. Весовые файлы MegaLoc находятся отдельно в `Models/models/megaloc/`.

```bash
git clone -b vps/docker-rebuild --single-branch https://github.com/chapaayy/Sorter.git
cd Sorter
cp .env.example .env
nano .env                  # только DOMAIN
./install.sh
```

Первоначальные DB/admin-секреты генерируются в защищённом `.env.generated`. Не коммитьте и не теряйте этот файл, `Models/`, `PhotoSorter/data/`, PostgreSQL volume. `install.sh` не должен пересоздавать существующие пароли.

## Хранение

| Путь | Владелец |
|---|---|
| `Models/models/`, `Models/cache/` | общие веса/кэш моделей (никогда не относятся к batch) |
| `PhotoSorter/data/references/SAM-xxxx/` | общая библиотека Образцов |
| `PhotoSorter/data/cache/megaloc/references/` | общий кэш эмбеддингов **только Образцов** |
| `PhotoSorter/data/uploads/<batch_id>/` | оригиналы отдельной партии |
| `PhotoSorter/data/outputs/<run_id>/megaloc/` | новый hardlink / прежняя копия и manifest |
| `PhotoSorter/data/runs/<run_id>/` | состояние и журнал запуска |
| `PhotoSorter/data/incoming/<upload_id>.part` | незаконченная передача |
| `postgres_data` | DB, версии миграций, жизненный цикл, сессии |
| `caddy_data`, `caddy_config` | HTTPS сертификаты/состояние |

Hard Links **не являются бэкапом**. Никогда не применять `docker compose down -v`, `docker system prune --volumes` или удаление `PhotoSorter/data` ради обновления.

## Проверки и дальнейшая работа

CI: `python -m compileall -q PhotoSorter/backend`, `PYTHONPATH=PhotoSorter/backend pytest -q PhotoSorter/backend/tests`. В CI тестовая PostgreSQL 17 и изолированные файлы в `tmp_path`. Реальные 189/1315-ФО fixtures не входят в репозиторий: полноценная сверка с эталонными отчётами и production rollout — только после разрешения.

Документация: [архитектура](docs/ARCHITECTURE.md), [файлы](FILE_INDEX.md), [жизненный цикл](docs/DATA_LIFECYCLE.md), [API](docs/API.md), [миграции](docs/MIGRATION_NOTES.md), [тесты](docs/TESTING.md), [бэкап](docs/BACKUP_RESTORE.md), [откат](docs/ROLLBACK.md), [развёртывание](docs/DEPLOYMENT.md), [дизайн этапа 3](docs/DESIGN_SYSTEM.md).

## Итог CI второго этапа

[GitHub Actions: 52 tests passed](https://github.com/chapaayy/Sorter/actions/runs/41954580354). Проверены Compose config и Python compile. Code только в [PR #2](https://github.com/chapaayy/Sorter/pull/2), который основан на ещё не объединённом PR этапа 1. Математика MegaLoc не изменена; на действующем VPS ничего не применено.

## Этап 3: новый Vue интерфейс (параллельно старому)

**URL:** прежний `/` и `/static/app.js` сохраняются неизменными. Новый UI запускается по **`/v3/`** и пока не назначен основным. Никаких операций на рабочем VPS не производилось.

| Раздел | Назначение |
|---|---|
| ФО | список партий, папка ФО (resumable PUT/PATCH), название, отдельная cursor-галерея, EXIF-превью и полноразмерный viewer |
| Образцы | двухпанельная библиотека SAM, загрузка папок, удаление/переименование SAM, блокировки при инференсе |
| Обработка | выбор партии/модели MegaLoc, порог 0.50–0.99, FIFO очередь, отмена, статус/измеренный ETA |
| Результаты | список завершённых запусков, SAM/группы и _Неопределено, полноразмерные фото, ZIP, отдельное явное подтверждение, retention |
| Логи | курсорные страницы, поиск/фильтр, режим tail, копирование и скачивание JSONL |
| Настройки | тёмная/светлая/системная тема, дисковый резерв, очередь, логи, retention и безопасный reaper кэша |

**Разработка UI на отдельной машине** (не запускать против реального продакшена):
```bash
cd PhotoSorter/frontend
npm ci
npm run dev
npm run build
npm run test
npm run test:e2e
```
Vite dev server на порту 5173, backend `/api` проксируется на localhost:8000. Статический Docker build использует отдельный `node:24-alpine` build stage; в Python/runtime Node не устанавливается. Архив ZIP через существующий streaming endpoint, отдельного server-side staging ZIP нет.

**Важно:** установка сборки и переключение `/` на Vue — не входят в этот этап. Для реального VPS сначала провести этап 4: независимый стенд, SSL/cookies, backup/restore, 189/1315-FО регрессии, CPU A/B, browser/phone UX.

### Проверенный CI третьего этапа

На `c0c1592b2f70db927498c9ffb9ca0f4f2770f453` проверены backend 56/56, frontend Vitest 9/9, TypeScript/Vite production build и Playwright 13 passed / 2 intentionally skipped (mobile-only сценарий пропущен для desktop). Исходники MegaLoc `app/recognition/` не менялись, работающий VPS не задействован.

- [GitHub Actions — backend](https://github.com/chapaayy/Sorter/actions/runs/41969359100)
- [GitHub Actions — Vue/Chromium/WebKit](https://github.com/chapaayy/Sorter/actions/runs/41969359113)

## Этап 4 — проверка безопасности, backup/restore и gate перед production

**Ветка:** `stage4/validation-backup-rollout`. Этапы 1–3 остались отдельными draft PR и **не слиты в `vps/docker-rebuild`**. **Production VPS, реальные пользовательские ФО и веса не изменены**.

Добавлены: полноценный CLI снимка с версированным manifest + SHA, снимок PostgreSQL custom-format, Models/models и Models/cache, изолированный восстановительный прогон в CI; comparator реального MegaLoc baseline/ZIP; synthetic 1315-FО zip/hardlink/storage lifecycle; только read-only staging probe; ограничение попыток логина и архивных путей, защита исторических SAM и проверки слишком больших изображений; реальный heartbeat трёх background workers (additive migration 0007); безопасный installer `--check`, no password reset, резервные условия upgrade.

**Статус:** код и доступные CI тесты могут быть зелёными, но система **НЕ объявлена production-ready**. Для этого всё ещё необходимы одинаковый реальный эталон 189 фото, 1315 реальных ФО (~6,4 ГБ), CPU A/B, полная Docker-runtime и TLS smoke, offsite backup/restore реального окружения, физический iPhone Safari и явное согласование запуска.

- [Матрица приёмки](docs/STAGE4_ACCEPTANCE.md)
- [Развёртывание и откат](docs/STAGE4_ROLLOUT.md)
- [Аудит безопасности](docs/STAGE4_SECURITY.md)
- [Changelog](docs/CHANGELOG.md)

Рабочее `/` по-прежнему отдаёт прежний интерфейс, `/v3/` — opt-in Vue после сборки. Математика MegaLoc `app/recognition/` не изменялась.
