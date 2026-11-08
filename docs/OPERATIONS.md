# Эксплуатация PhotoSorter — очереди, превью, логи и диск

**Текущая версия:** все сервисы входят в `main`. При изменении действующего VPS нужны проверенный бэкап, контроль активных задач и предварительная диагностика.

## Сервисы

`caddy` — HTTPS; `api` — авторизованные маршруты, upload/metadata; `worker` — один MegaLoc inference; `thumbnail` — CPU-limited WebP задачи; `cleanup` — retention, упавшие outputs, preview cache и старые .part; `postgres` — транзакции и долговременные очереди.

`Models/models` — веса; `Models/cache` — torch/huggingface; `PhotoSorter/data` — PhotoSorter uploads, refs, outputs, thumbnails. Docker volumes и `.env.generated` сохраняются. Нельзя выполнять `docker compose down -v`.

## Загрузка и миниатюры

1. `POST /api/uploads` с предварительно сохранённым `client_upload_id` (идемпотентный повтор после пропажи ответа), PATCH offset блоками 16 МиБ, `finish` — контроль фактического размера, SHA-256 и Pillow. Direct PUT сохранён для совместимости, новый UI использует PATCH.
2. В транзакции успешной финализации создаётся `thumbnail_tasks`. Запрос **не ждёт** PNG/JPEG/TIFF decoding.
3. Низкоприоритетный Worker создаёт WebP 480px q78, применяет EXIF orientation и преобразование ICC→sRGB для корректных профилей, использует оригинал только для чтения.
4. `GET /api/thumbnails/{UUID}`: 202 пока pending, 200 WebP после готовности, 404 нет фото. `POST /api/thumbnails/{UUID}/retry` для failed.
5. После crash устаревшие running задачи переclaim'ятся через 5 минут, максимум 3 попытки до ручного retry; общий cache очищается только если checksum больше никому не принадлежит и прошёл grace 24 часа.
6. `DELETE /api/uploads/{id}` — только незаконченная загрузка. Каждые ~10 минут проверяются `.part` старше 30 суток без активных операций. **Ни один finalized оригинал автоматически по TTL .part не удаляется.**

### Восстановление после сбоя сети/VPN

- Если ответ POST/PATCH/finish потерялся после фактической записи данных, браузер повторяет запрос с экспоненциальным ожиданием, сверяет реальное состояние через `GET /api/uploads/{id}` и возобновляет с подтверждённого смещения. Сетевые ошибки (status=0) ожидают возобновления, повторные 5xx имеют ограниченное число попыток. Кнопка «Пауза» прерывает ожидание; недосланное остаётся на VPS.
- При повторном открытии `/fo/{batch_id}` компонент «Незавершённые загрузки» читает `GET /api/batches/{id}/pending`: ID, имя, размер, реальное число байт на диске и SHA-256 всей уже принятой части (до 60 МиБ на фото). Полные `.part` автоматически пробуют `POST /api/uploads/{id}/finish` (повторная передача оригинала **не нужна**). Недокачанные — «Продолжить» с выбором исходного файла. Сначала сравниваются имя, размер и SHA-256 уже полученного начала. После потери файловых прав браузера оригинал нельзя прочитать без повторного выбора пользователем.
- «Отменить» имеет отдельное подтверждение и вызывает `DELETE /api/uploads/{id}` **только для выбранной незавершённой** записи. Готовые фотографии и результаты не затрагиваются. Отмена нужна, если исходник недоступен, повреждён либо загрузка не нужна.
- `/processing` отображает партию с `pending>0`, но запрещает запуск MegaLoc до завершения/отмены оставшихся передач и даёт ссылку на партию. Миниатюры ready не гарантируют `pending=0`.
- При невозможности финализации не удаляйте .part вручную: проверьте наличие файла, контроль размера, правильность формата изображения, дисковые ошибки и логи API. При пропавшем временном файле можно отменить именно эту недозагруженную запись. Старая автоматическая TTL-очистка (30 дней) сохраняется.

### Диагностика остановки загрузки ФО

Одновременная инициализация файлов одной партии использует блокировку PostgreSQL `FOR NO KEY UPDATE`: прежнее повышение `FOR SHARE` → `UPDATE` могло приводить к взаимным блокировкам при 5–10 параллельных передачах. Очередь браузера показывает первый HTTP-код ошибки сразу и останавливает начальный поток после трёх ошибок без успешного файла, сохраняя возможность докачки. Ноль процентов во время «Подготовка партии» сам по себе не доказывает сбой.

При повторной проблеме проверяйте `docker compose --env-file .env --env-file .env.generated logs --tail=120 api postgres` и сообщение в панели. Не очищайте `PhotoSorter/data/incoming`, не удаляйте объекты uploads и не запускайте `docker compose down -v`: незаконченные передачи могут возобновиться.

## MegaLoc

`POST /api/runs`: FIFO до 20 queued, один running, DB advisory/leader locks. `GET /api/runs/{id}` отображает `queue_position`. `POST .../stop` queued→stopped, running→stopping→stopped; при crash running→interrupted. Никаких недостоверных обещаний продолжить inference с того же кадра. Логика FO→groups→SAM прежняя.

## Логи и диск

`/api/logs/{run_id}/page?limit=200&cursor=...`: event lines по сегментам, курсор может устареть после ротации (422, начать заново). Legacy `/api/logs/{run_id}` показывает хвост 250 событий. Docker ограничен max-size=10m/max-file=3.

`/api/system/status` — очереди, p95 API и reserve; `/api/storage/usage` — inode-dedup по категориям и DB estimate; `/api/logs/usage` — журнал. На 80% диска warning, на 90% critical. При 507 освободить место ручной **подтверждённой** очисткой/расширить диск, а не безусловно стирать незагруженные архивы.

## Тестирование и откат

CI запускает PostgreSQL 17, compile Python, Compose config и unit/integration тесты. Full Docker runtime с CPU PyTorch и A/B на фактическом VPS не проводились. Документы: [PERFORMANCE](PERFORMANCE.md), [ROLLBACK](ROLLBACK.md), [BACKUP_RESTORE](BACKUP_RESTORE.md).

## Границы проверок

Сборка Python/Compose и 52 автоматических теста завершились успешно: [GitHub Actions 41954580354](https://github.com/chapaayy/Sorter/actions/runs/41954580354). Full production smoke test и A/B по реальным CPU, сети и 1315 ФО не выполнялись. Это остаётся обязательным до внедрения.

## Heartbeat и операторские состояния

Три независимых процесса периодически (раз в 10 секунд) пишут в `service_heartbeats` отметку присутствия; API `/api/system/status.services` возвращает `alive:bool` (свежее ≤35 секунд), `last_seen`. Пустая очередь заданий не означает, что process alive. После остановки процесса реальная отметка устаревает, `Settings` показывает ошибочное состояние, вместо фиктивного «работает».

После обновления Schema 0007 и запуска Compose проверить worker, thumbnail, cleanup heartbeat **при простое и во время инференса**. Если Process не отвечает, сверить Docker ps, logs, DB network и RAM; не запускать второй worker в обход global advisory lock.

Скрипт `install.sh --check` теперь проверяет допустимость cpuset на текущем хосте; обновления существующего volume требуют реального backup и отдельного ack. См. [STAGE4_ROLLOUT](ROLLOUT.md).


## Единый beta pipeline

Очередь ФО и подготовок образцов — только `work_queue.seq`; загрузка образцов всегда доступна через `/api/reference-imports` и сохраняет файлы в `reference_staging`. После полной подготовки публикуется неизменяемая версия библиотеки. Обе версии планировщика и условные флаги переключения удалены. Приёмка — тесты на пустой базе, докачку, FIFO, публикацию и браузеры Chromium/WebKit. Текущая архитектура: [REFERENCE_PIPELINE](REFERENCE_PIPELINE.md).

## ZIP и автоудаление

Полный ZIP атомарно формируется до состояния `completed`. Ошибка ZIP не уничтожает готовые результаты MegaLoc: запрос повторной подготовки сохраняется в `archive_retries` и исполняется cleanup worker, без инференса. При удалении партии удаляется и `.archives/`.

Настройка срока от минуты до месяцев действует только на новые успешные обработки, чтобы смена параметра не удалила существующие партии внезапно. Активные скачивания защищены `batch_operations`.

## XFeat (ветка feature/ad-recognition, тестовый ручной режим)

После завершения MegaLoc и ZIP: установить проверенные веса в API через
`docker compose exec api python -m app.screen_detection.cli --install`,
проверить на Worker командой `docker compose exec worker python -m app.screen_detection.cli --verify`,
затем `--run-id RUN_ID --limit 20`. Результаты и ошибки поиска находятся
в исходной галерее «Результаты» → «Диагностика XFeat».
Безопасное явное удаление неиспользуемых кэшей старше недели:
`docker compose exec worker python -m app.screen_detection.cli --prune-cache`.
Эти команды не изменяют PostgreSQL очередь, MegaLoc, ZIP или volumes.


## Opt-in ad recognition: one CPU task until ZIP

In «Макеты рекламы» enable after explicit verified model installation.
The new flag is read only at a FO's FIFO claim; MegaLoc and archived
historical tasks remain unchanged. The worker logs stages XFeat,
DINOv2/OCR, quality/best, and full ZIP. ZIP is not available
before the full set finishes. Any systemic model failure stops the run
without publishing a deceptive completed archive; error details remain
in run logs/diagnostics.

For a completed run, open «Результаты» → «Лучшие кадры по рекламным
макетам». The downloaded full ZIP includes originals plus
`Best_by_layout` and separate `Review_required`. A filtered
SAM ZIP includes only its corresponding photos. On a damaged ZIP,
request existing ZIP-only recovery — it must NOT start XFeat/DINO/OCR.
Deleting the batch removes all its outputs/ZIP; global layouts remain.


## Модели и прогресс подготовки Образцов

**Настройки → Модели** предоставляет контролируемую установку всех
четырёх CPU-моделей. `GET /api/models` показывает проверенное состояние
и фоновую установку, `POST /api/models/{megaloc|xfeat|dinov2|paddleocr}/download`
запускает одну фиксированную команду установки в API. Нельзя
отправить произвольный путь или shell-команду через API.
Одновременные установки отвергаются. Работающие интегрированные
распознавания защищены от смены модели. Проверенные файлы лежат
в `Models/models/`, служебный кэш/логи в `Models/cache/`.

Если в очереди долго 0%, а Worker активно нагружает CPU,
сначала посмотрите `progress_stage` в деталях: проверка,
загрузка, вычисление признаков или публикация. Во время
`extracting` счётчик `completed_count/total_count` сохраняется
по мере получения каждого готового вектора. Фактическое завершение
публикуется транзакционно только после полного набора.
Не перезапускайте Worker посреди текущей подготовки: после
обновления такого VPS понадобится повторить остановленную подготовку
через меню очереди; исходные файлы и веса не стираются.

При ручной диагностике CLI запускать из папки с `compose.yaml`:
```bash
cd /opt/Sorter
docker compose --env-file .env --env-file .env.generated ps
docker compose --env-file .env --env-file .env.generated logs --tail=100 worker api
```
Запуск `docker compose` из `/root` без `-f` выдаёт
`no configuration file provided: not found` — это не ошибка модели.
