# Приёмка бета-версии PhotoSorter

**Статус: автоматические CI-проверки пройдены; реальная эксплуатационная приёмка ещё не завершена.** Ниже критерии, а не заявление, что все они уже пройдены.

## Обязательные ворота перед переключением VPS

| Ворота | Требование | Статус |
|---|---|---|
| P0: целостность | Оригиналы ФО/Образцы и исторические manifests/ZIP сравниваются по SHA-256 | В CI только синтетические файлы; реальные ФО нужно проверять отдельно |
| P0: MegaLoc baseline | 189 ФО, 27 групп, 3 uncertain при наличии проверенного эталона; точное сравнение SAM, порядка, score/top/verdict | **Блокер:** golden baseline и те же веса/фото не доступны |
| P0: рабочий объём | 1315 ФО, ~6.4 ГБ, сеть/throughput, ZIP, CPU/RAM/disk/API latency | В CI проверено 1315 **маленьких синтетических hardlink-записей**; реальные ГБ НЕ прогонялись |
| P0: backup | Offsite зашифрованный снимок PG+ФО/Образцы/outputs/Models/.env.generated; snapshot после остановки записей | CLI реализован; в CI реальный pg_dump/pg_restore двух disposable БД, не реального VPS |
| P0: restore | Восстановление на отдельный пустой Linux staging и повторная проверка оригиналов/ZIP/очереди/авторизации | CI disposable проверен, реальное offsite test restore **не выполнено** |
| P0: production approval | Явное согласие владельца после просмотра отчёта и копии | **Не получено**, rollout запрещён |
| P1: Docker runtime | Полная сборка Python+torch CPU и холодный boot Compose, Caddy TLS, uptime/health, reboot | Compile/Compose config/Caddy syntax CI проверены, full runtime/reboot нет |
| P1: mobile Safari | Физический iPhone Safari, мелкий экран 375px, upload, viewer, ZIP, темы | WebKit Playwright mock API покрыт, физический телефон не проверен |
| P1: hardlinks | inode/dev/hash реального Linux data volume, cross-FS fallback, concurrent-delete/read | Linux CI/tmpfs сценарии проверены, на фактическом 200GB mount не проверены |
| P1: TTL и restart | В реальном времени retention +2 calendar months/7 days, restart worker/cleanup | SQL/тесты проверены, реальный reboot не проверен |
| P1: CPU A/B | Baseline 8 threads vs Worker 7/cpuset 0–6, p95 API во время инференса | Протокол и read-only probe готовы, фактического A/B нет |
| P1: секреты | Сохранение существующих .env.generated, admin login, auth, Origin, rate limit | Изолированные CLI/pytest проверки; production не менялся |

## Доказательства CI, которые есть в репозитории

- `.github/workflows/ci.yml`: PostgreSQL17/Python, Bash syntax, Compose config, Caddy config validation, Pytest; отдельная disposable PG dump→restore, checksum и link inode; Vue typecheck, unit, Chromium/WebKit desktop и mobile UI.
- `PhotoSorter/tools/maintenance/compare_baseline.py`: строгая проверка двух предоставленных manifests и двух ZIP. Не создаёт фиктивные 189-ФО результаты.
- `PhotoSorter/tools/maintenance/staging_probe.py`: только HTTP GET, замер p50/p95, rps, API/worker/disk, опционально read-only Docker stats. Удалённые хосты требуют явного opt-in.
- `PhotoSorter/backend/tests/test_stage4_load.py`: 1315 маленьких синтетических ссылок, открытие результата по страницам, zipstream-ng, checksum, однопартийная очистка.
- `PhotoSorter/tools/maintenance/snapshot.py`: snapshot/verify/restore-test с fail-closed ограничениями (только пустой staging DB с именем sorter_restore_*, отдельный каталог с STAGING_ONLY).

## Приёмочные показатели

Перед реальным развёртыванием сохранить в отдельном отчёте: аппаратная конфигурация и допустимые CPU IDs, commit+MegaLoc weights signature, размер/число фото и датасет, p50/p95 API, throughput upload и ZIP, stage inference wall time, RAM/CPU/disk, inode/hashes, логи worker/cleanup, время test restore, фото physical Safari, скриншоты тем/галерей, точка rollback. Сравнивать при одинаковых фото/весах/нагрузке, минимум три прогона, никаких придуманых скоростей.

**Зелёный CI не равен полной приёмке.** По запросу владельца `frontend/static` удалён из кода, Vue стал единым сайтом на `/`; перед чистой установкой или удалением старых данных по-прежнему нужны зафиксированные решения о резервной копии и объёме очистки.


## Единый beta pipeline

Очередь ФО и подготовок образцов — только `work_queue.seq`; загрузка образцов всегда доступна через `/api/reference-imports` и сохраняет файлы в `reference_staging`. После полной подготовки публикуется неизменяемая версия библиотеки. Обе версии планировщика и условные флаги переключения удалены. Приёмка — тесты на пустой базе, докачку, FIFO, публикацию и браузеры Chromium/WebKit. Текущая архитектура: [REFERENCE_PIPELINE](REFERENCE_PIPELINE.md).
