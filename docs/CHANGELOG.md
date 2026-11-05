# Changelog OUTDOOR PhotoSorter

## Beta 0.1.0-beta.1 — main
- Единственный Vue 3 сайт на `/`, разделы `/fo`, `/references`, `/processing`, `/results`, `/logs`, `/settings`, `/login`.
- Старый `frontend/static` удалён; `/v3/` и `/static/*` не обслуживаются. Единственный источник кода — `main`. Vite, Vue Router, Playwright, pytest и Docker smoke проверяют единый root-адрес.
- API, PostgreSQL, MegaLoc math и физические фотографии не изменяются этой правкой GitHub. Live VPS обновляется отдельно.


## История разработки: проверка безопасности, backup и rollout
- CLI `snapshot.py`: согласованный снимок данных, PostgreSQL custom dump, Models/models+cache, учет Hard Links, SHA-256, verify и только изолированное восстановление.
- CI PostgreSQL17: реальный pg_dump→pg_restore на disposable DB, восстановление тестовых фото/Образцов, контроль записи и inode.
- `compare_baseline.py`: детальный diff SAM/group/uncertain/score/candidate ranking + ZIP CRC, не требует нейросети.
- 1315 синтетических ФО + ZIP/SAM/cleanup/retention regression; отделено от реального 6.4 GiB benchmark.
- `staging_probe.py`: только GET, p50/p95, RPS, возможные реальные service/disk и docker stats для staging.
- Безопасный `install.sh --check`, восстановление секретов, no credential reset/up без подтверждённого backup.
- Security: login throttling, rejection of 30M+ pixel bombs, ZIP Slip and historical SAM path protection.
- Миграция `0007_service_heartbeat.sql`, процессный heartbeat и UI статус трёх служб; исправлен парсер SQL комментариев.
- Не меняет MegaLoc math, не перезаписывает старые ZIP/UI, не трогает VPS.

## История разработки: интерфейс Vue 3
- Новый opt-in `/v3/`, Vue 3+TypeScript+Vite+Pinia, 6 вкладок, темы, мобильный WebKit, virtual grid, полный ZIP с отдельным подтверждением; legacy `/` сохранён.
- [PR #3](https://github.com/chapaayy/Sorter/pull/3).

## История разработки: очереди, превью и производительность
- WebP tasks, sequential MegaLoc FIFO, cursor pagination, log rotation, disk admission and CPU staging hypothesis.
- [PR #2](https://github.com/chapaayy/Sorter/pull/2).

## История разработки: партии, Hard Links и retention
- Additive SQL migrations, batch ownership, exclusive hardlinks, full deletion state machine, confirmed ZIP + 2 month UTC retention, rollback documents.
- [PR #1](https://github.com/chapaayy/Sorter/pull/1).
