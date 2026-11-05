# Тесты, baseline и пределы проверки

## Команды

```bash
python -m compileall -q PhotoSorter/backend
PYTHONPATH=PhotoSorter/backend python -m pytest -q PhotoSorter/backend/tests
docker compose --env-file .env --env-file .env.generated config --quiet
```

CI `.github/workflows/ci.yml` поднимает **временный Postgres 17** (`sorter_test`) и запускает те же Python tests на Ubuntu Python 3.11, не подключаясь к VPS. Unit без PostgreSQL можно запускать отдельно — DB cases будут пропущены.

| Проверка | Где |
|---|---|
| 0.50 grouping, функции ФО→группы→SAM | `test_grouping.py` |
| прогресс/ETA без вымышленных процентов | `test_progress_ring.py` |
| hardlink inode/hash, unlink одного имени, EXDEV, duplicate | `test_stage1_lifecycle.py` |
| старая SQL схема + additive migration, idempotency | `test_stage1_lifecycle.py`, disposable schema |
| owned deletion 0/2 runs, другая партия, references | `test_stage1_lifecycle.py` |
| active ZIP/upload lease, running/queued job, retry after exception | `test_stage1_lifecycle.py` |
| архив zipstream читабелен, прежний SAM layout | `test_stage1_lifecycle.py` |
| +2 календарных месяца, 7-day warning/extension; latest-run guard | `test_stage1_lifecycle.py`; production clock simulation остаётся для этапа 4 |
| 189/1315 реальных ФО и профиль CPU | **не хранится в repo, не заявлять пройденным** |
| полная restore проверка, TLS, Docker on VPS | **только на staging с разрешением** |

Тесты обязаны писать исключительно в `tmp_path` и disposable DB; не подключать `DATABASE_URL` производственной системы. CI не заменяет восстановление архивов и длительное тестирование на Linux volume, которое запланировано в этапе 4.

## CI baseline (этап 1)

GitHub Actions runs `41949026787` и `41949033874`: **33 passed**, Python compile и `docker compose config --quiet` successful (commit `cd6a4cf1`). Дополнительно проверяются удаление чужих файлов/symlink escape, структура миграций и конца календарного месяца. Количество тестов в CI может увеличиваться после следующих исправлений; итоговый отчёт должен ссылаться на конкретный SHA. Настоящий `docker compose up` и model inference с большими фотографиями на VPS не выполнялись.

## Stage 2 CI tests и пределы доказательств

`PhotoSorter/backend/tests/test_stage2_platform.py` проверяет финализацию→thumbnail queue, WebP EXIF и 480px, повтор stale-task, checksum cache reuse между партиями, GC после исчезновения всех владельцев, ошибки preview, 1001 синтетическую gallery metadata запись, FIFO/stop/single-running, JSONL rotation/cursor, reserve 507.

`PhotoSorter/backend/tests/test_stage2_transfers.py` проверяет прямой PUT, PATCH offset/resume, mismatch SHA, cancel только pending, ZIP disconnect и release IO lease, original viewer read lease. Все файлы в `tmp_path`, PostgreSQL 17 только disposable CI service. Дополнительно выполняются все регрессии этапа 1 + MegaLoc math (без изменения алгоритмов).

Ручные проверки **не выполнялись**: real 189/1315 photo files, полный Docker build с PyTorch, настоящие 8-vCPU VPS нагрузочные A/B, сеть 350–400 Мбит/с, Safari UI (этап 3), full backup/restore. Замеры будут честно получены только после разрешения. Порядок A/B — в [PERFORMANCE](PERFORMANCE.md).

## Фактически выполненный CI для stage2

GitHub Actions workflow `41954580354` на `4f6212729ef7277091eb134141f4a18b80375134`: `52 passed in 4.52s`, `python -m compileall` и `docker compose config --quiet` прошли. Тестовая PostgreSQL 17 — временный CI service, а не действующий VPS. Ни один файл `app/recognition/` в diff stage1→stage2 не менялся.

## Stage 3 — browser/API verification

Frontend commands:
```bash
cd PhotoSorter/frontend
npm ci
npm run build  # vue-tsc --noEmit + Vite static /v3/ bundle
npm run test   # Vitest contracts in tests/
npx playwright install chromium webkit
npm run test:e2e
```
`.github/workflows/stage3-vue.yml` запускает Node 24, npm ci с точным package-lock, TypeScript/Vite, Vitest и Playwright Chrome desktop, WebKit desktop, iPhone-size WebKit. E2E подменяет `/api` тестовыми ответами; **это проверка фронтенд-потоков, не реальных сетевых фото**.

`backend/tests/test_stage3_ui_api.py` на временных директориях и тестовой PostgreSQL проверяет rename/delete SAM, запрет во время queued обработки, защиту от traversal и раздельность legacy `/` и Vue `/v3/`.

Не подтверждено: реальный iPhone Safari, реальные 189/1315 изображений, полноценный Docker build с CPU PyTorch, реальная сеть/диск/время финиша ZIP, отказоустойчивость прерывания на нескольких API workers, production backup/restore. **Этап 4 — обязательная приёмка**; приложение пока opt-in и не стало основным UI.
