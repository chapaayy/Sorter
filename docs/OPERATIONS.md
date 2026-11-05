# Stage 2 — эксплуатация очередей, превью, логов и защиты диска

**Внимание:** вся новая инфраструктура только в GitHub stage2 branch, **не запущена на рабочем VPS**. Применение миграций и новой очистки требует разрешения, бэкапа и проверки восстановления на отдельном стенде.

## Сервисы

`caddy` — HTTPS; `api` — авторизованные маршруты, upload/metadata; `worker` — один MegaLoc inference; `thumbnail` — CPU-limited WebP задачи; `cleanup` — retention, упавшие outputs, preview cache и старые .part; `postgres` — транзакции и долговременные очереди.

`Models/models` — веса; `Models/cache` — torch/huggingface; `PhotoSorter/data` — PhotoSorter uploads, refs, outputs, thumbnails. Docker volumes и `.env.generated` сохраняются. Нельзя выполнять `docker compose down -v`.

## Загрузка и миниатюры

1. `POST /api/uploads`/direct PUT, PATCH offset, `finish` — текущие checksum/Pillow проверки.
2. В транзакции успешной финализации создаётся `thumbnail_tasks`. Запрос **не ждёт** PNG/JPEG/TIFF decoding.
3. Низкоприоритетный Worker создаёт WebP 480px q78, применяет EXIF orientation и преобразование ICC→sRGB для корректных профилей, использует оригинал только для чтения.
4. `GET /api/thumbnails/{UUID}`: 202 пока pending, 200 WebP после готовности, 404 нет фото. `POST /api/thumbnails/{UUID}/retry` для failed.
5. После crash устаревшие running задачи переclaim'ятся через 5 минут, максимум 3 попытки до ручного retry; общий cache очищается только если checksum больше никому не принадлежит и прошёл grace 24 часа.
6. `DELETE /api/uploads/{id}` — только незаконченная загрузка. Каждые ~10 минут проверяются `.part` старше 30 суток без активных операций. **Ни один finalized оригинал автоматически по TTL .part не удаляется.**

## MegaLoc

`POST /api/runs`: FIFO до 20 queued, один running, DB advisory/leader locks. `GET /api/runs/{id}` отображает `queue_position`. `POST .../stop` queued→stopped, running→stopping→stopped; при crash running→interrupted. Никаких недостоверных обещаний продолжить inference с того же кадра. Логика FO→groups→SAM прежняя.

## Логи и диск

`/api/logs/{run_id}/page?limit=200&cursor=...`: event lines по сегментам, курсор может устареть после ротации (422, начать заново). Legacy `/api/logs/{run_id}` показывает хвост 250 событий. Docker ограничен max-size=10m/max-file=3.

`/api/system/status` — очереди, p95 API и reserve; `/api/storage/usage` — inode-dedup по категориям и DB estimate; `/api/logs/usage` — журнал. На 80% диска warning, на 90% critical. При 507 освободить место ручной **подтверждённой** очисткой/расширить диск, а не безусловно стирать незагруженные архивы.

## Тестирование и откат

CI запускает PostgreSQL 17, compile Python, Compose config и unit/integration тесты. Full Docker runtime с CPU PyTorch и A/B на фактическом VPS не проводились. Документы: [PERFORMANCE](PERFORMANCE.md), [ROLLBACK](ROLLBACK.md), [BACKUP_RESTORE](BACKUP_RESTORE.md).

## Итог проверок stage2

Сборка Python/Compose и 52 автоматических теста завершились успешно: [GitHub Actions 41954580354](https://github.com/chapaayy/Sorter/actions/runs/41954580354). Full production smoke test и A/B по реальным CPU, сети и 1315 ФО не выполнялись. Это остаётся обязательным до внедрения.

## Stage 4 heartbeat и операторские состояния

Три независимых процесса периодически (раз в 10 секунд) пишут в `service_heartbeats` отметку присутствия; API `/api/system/status.services` возвращает `alive:bool` (свежее ≤35 секунд), `last_seen`. Пустая очередь заданий не означает, что process alive. После остановки процесса реальная отметка устаревает, `Settings` показывает ошибочное состояние, вместо фиктивного «работает».

После обновления Schema 0007 и запуска Compose проверить worker, thumbnail, cleanup heartbeat **при простое и во время инференса**. Если Process не отвечает, сверить Docker ps, logs, DB network и RAM; не запускать второй worker в обход global advisory lock.

Скрипт `install.sh --check` теперь проверяет допустимость cpuset на текущем хосте; обновления существующего volume требуют реального backup и отдельного ack. См. [STAGE4_ROLLOUT](STAGE4_ROLLOUT.md).
