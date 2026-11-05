# OUTDOOR PhotoSorter — VPS / MegaLoc (этапы 1–2)

Приватный фотоотчёт рекламных конструкций. MegaLoc сначала группирует **только ФО** (порог по умолчанию 0.50), затем сопоставляет группы с общей библиотекой SAM. Нейронная математика, постоянные модели и кэш эталонов в этапе 1 не изменялись.

## Статус веток и безопасность

- Стабильная исходная ветка: `vps/docker-rebuild`.
- Разработка этапа 1: `stage1/batch-lifecycle-hardlinks` (отдельная ветка, не production).
- Изменения этапа 1 — новая схема и фоновые операции удаления; **не запускать на действующем VPS без резервной копии, проверки восстановления и явного разрешения**.
- Никаких удалений, миграций и развёртываний на VPS в ходе работы над веткой не выполнялось.
- **Этап 2:** `stage2/performance-thumbnails-queue`, отдельная ветка от этапа 1. Этапы 3 (Vue UI) и 4 (production validation) не реализованы.

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
