# Производительность PhotoSorter — CPU, API, загрузка и baseline

## Известные исторические наблюдения (из ТЗ, не новые измерения)

- Пример старого запуска: 1315 ФО, ~31 группа, ~314 сек; ~303.7 сек уходило на инференс.
- Исходный Worker: Docker `cpus: 8`, `PHOTOSORTER_CPU_THREADS=8`, batch=4, prefetch=2.
- При инференсе сайт иногда тормозил. Caddy HTTP/1.1 ранее увеличил upload throughput в пользовательском тесте. Настройки TLS/HTTP Caddy **не менялись**.

## Гипотеза CPU на 8-vCPU Linux

- `worker` cpuset 0–6, `cpus:7`, 7 потоков. CPU7 остаётся доступным API/DB/Caddy, но это **не гарантированно физически выделенное ядро**.
- `thumbnail` отдельный контейнер, 0.35 CPU, 512 MiB RAM, nice+10; `cleanup` 0.25 CPU/256 MiB.
- `batch_size=4`, `prefetch_workers=2` сохранены. Математика MegaLoc, модель/веса и кэширование ФО не изменялись.
- На VPS с иным cpuset до запуска настроить `PHOTOSORTER_WORKER_CPUSET`, проверить Docker cgroup CPU allowed set. Не развёртывать без бэкапа и отдельного разрешения.

## A/B протокол — выполнять только после разрешения

1. Взять одни и те же реальные/лицензированные тестовые ФО, SAM и checkpoint SHA, подготовить восстановимый staging. Снять baseline до изменения CPU: worker 8/8, без cpuset. Для B — worker 7/7/cpuset 0–6.
2. По 3–5 прогонов (после warmup) измерить wall time, инференс ФО, p50/p95 API при загруженном Worker, загрузку Mbps, средний RSS, CPU, disk I/O, ошибки.
3. Read-only latency CLI: `python PhotoSorter/tools/benchmark_api.py --url http://127.0.0.1:8000/api/health --count 100 --concurrency 4`; повторить с реальным authenticated API через `--cookie` **только на staging**.
4. Сравнивать только при одинаковых внешних условиях. Если p95 хуже/время инференса значительно растёт — откатить cpuset или потоковые настройки.
5. Записать в отчёт hardware, versions, SHA, нагрузку и реальные цифры. **На рабочем VPS в этапе 2 A/B не проводилось, нельзя заявлять рост скорости.**

## Защита места/логов/отзывчивости

- `statvfs` до и во время upload; резерв = min(12 GiB,max(256 MiB,6% ёмкости mount)), можно переопределить `PHOTOSORTER_MIN_FREE_BYTES` осознанно. 507 запрещает опасные новые записи, не удаляет завершённые ФО.
- Run logs ограничены 5×4 MiB (~20 MiB/run) и global budget 512 MiB; Docker JSON logs 10m×3 для каждого контейнера.
- `/api/system/status` содержит p50/p95 HTTP header latency по последним 2048 запросам, **не полную длительность ZIP-stream**. CPU quota не является выделением физического ядра.
- `/api/storage/usage` считает физические байты файлов по inode, плюс отдельно оценивает DB `pg_database_size`; PostgreSQL WAL, Docker daemon, Caddy volumes нельзя точно определить из API mount, они отмечены отдельно.
- Текущий stage2 CI проверяет функциональные контракты в disposable DB, 1001 синтетическую metadata запись, но **не** пиковые Mbps/CPU и 1315 полноразмерных реальных фото.

## Read-only probe и сравнение реальных результатов

- `PhotoSorter/tools/stage4/staging_probe.py`: локальные GET /api/health, при отдельном cookie-файле (0600) GET /api/system/status и /api/storage/usage, p50/p95 latency, RPS/HTTP codes. Если указать `--docker-stats`, читается `docker stats --no-stream` (CPU%, memory, net/block IO), без SSH/запуска Worker. Удалённый staging хост требует `--allow-remote-staging`; **не запускать против production** без разрешения.
- Инструмент `compare_baseline.py`: два сохранённых manifests, optional ZIP CRC, строгий diff порядка групп, SAM, top candidates, uncertainties, score. Имена одинаковых файлов в разных каталогах требуют явных `--golden-root/--actual-root`, чтобы не склеивать дубликаты.
- Исторический ориентир ~314s / 1315 фото указан в исходном ТЗ и НЕ является stage4 benchmark. Новый 1315 synthetic ZIP test не измеряет MegaLoc.
- Рабочий сценарий A/B: одинаковые golden weights+фото, три и более прогона в cpu 8 vs cpu7/cpuset, базовые и нагрузочные p95, upload/ZIP, RSS, disk, сравнение и сохранение JSON evidence. Инференс в CI без модели не производился.
