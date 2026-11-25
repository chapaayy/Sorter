# Финальная приёмка Storage V2 — отчёт на 25.11.2026

**Этап 10 открыт.** Ниже фактически полученные результаты и отдельные обязательные проверки; не разрешение на production rollout.

## Доказательства
- Закрывающий этап 9: 5ce1808, [CI 45494437011](https://github.com/chapaayy/Sorter/actions/runs/45494437011), 7/7.
- Реализация этапа 9: 6b14fb0, CI 45492993969, 378 backend tests + 28 subtests, три браузерных набора, restore и Docker runtime. Реальные offline MegaLoc, повторный deploy, проверка TLS/PG/файлов, сохранение модели/эмбеддингов, проверка дискового резерва обновлятора. Эти результаты относятся к предыдущей проверенной ревизии, не заменяют финальную проверку.
- Stage 10: 24dc058 — интерактивная настройка, b293bc9 — настоящий Ubuntu VM/systemd/reboot сценарий, 11f0cbd — реальная нагрузка, 8ee4607 — исправление тестов, cleanup и TLS источника корпуса.
- Первый [release run 45497828371](https://github.com/chapaayy/Sorter/actions/runs/45497828371): load остановлен до обработки из-за TLS сертификата COCO. Новый источник: HTTPS HF mirror, закреплённая ревизия fbbee70f52f540987cca6936c9f1d7b1ff969ad1, SHA-256 4f7e2ccb2866ec5041993c9cf2a952bbed69647b115d0f74da7ce8f4bef82f05. Никаких фиктивных метрик.

## Обязательные критерии
| Критерий | Статус |
|---|---|
| Единый контракт, отсутствие старых mounts | Реализовано и проверялось этапами 2–9; финальная сверка и регрессия отдельно |
| Чистая Ubuntu, автоматическая установка Docker и systemd, перезагрузка, обновление API | **ПРОЙДЕНО** — 45505109384 / 138838181284, фактическое здоровье всех 6, hashes/DB/TLS и реальное API update |
| Основной функционал, права, квоты, восстановление | 42e678b и e8675d2: обычный CI 7/7, реальные restore/update/offline MegaLoc; комплексная нагрузка ещё не подтверждена |
| 10 различных реальных фото, 1 тестовое видео, повторная сортировка, 3 цикла | Компактный сценарий по решению владельца; результат ожидается |
| Фактические CPU/RAM, disk peak, скорость сверки и Chromium, ZIP TTL (ускоренное наблюдение последних 60 секунд) | Нет измеренного отчёта, критерий открыт |
| Долговременный рост, очистка, сохранение модели после обновления | Предыдущие точечные проверки есть; комплексный цикл не подтверждён |
| Финальный CI | 42e678b, e8675d2, 2d2bbc4 обычный push CI 7/7; VM gate PASS; обязательный load и окончательная ревизция ещё открыты |
| PR без merge | PR #22 открыт в draft, не объединён |

COCO — реальные публичные фотографии общего назначения, не размеченный набор конструкций SAM. Видео в нагрузочном сценарии сгенерированы для проверки кодеков. Даже успешный load не доказывает точность сортировки рекламных конструкций. Реальная Ubuntu VM проверяет localhost TLS, а не публичный ACME конкретного VPS. Локальная среда Debian без Docker/KVM; никакая ручная имитация systemd не принимается за успех. Метрики будут доступны только при фактическом выполнении job (JSON artifact). 

## Subsequent checkpoint
- [PR #22](https://github.com/chapaayy/Sorter/pull/22) opened as draft; main untouched, no merge.
- [Release 45498523215](https://github.com/chapaayy/Sorter/actions/runs/45498523215) downloaded and verified the pinned COCO archive but failed before processing due to ZipInfo sorting; corrected. A load report has not yet been produced.
- Backend CI 45498523284 revealed an old test fixture expecting unmanaged runs to be deleted. The updated fixture tests canonical managed cleanup and verifies unmanaged files survive. New API quota rejection probe added to the release load.


## Проверка после исправления VM
- [CI 45499161838](https://github.com/chapaayy/Sorter/actions/runs/45499161838) — 42e678b, 7/7; [CI 45501539115](https://github.com/chapaayy/Sorter/actions/runs/45501539115) — e8675d2, 7/7. Backend 379 passed, 28 subtests, one warning. Docker runtime подтвердил сохранность модели/эмбеддингов, обновление двух коммитов, восстановление данных/PG/TLS, ограничение журналов и cleanup BuildKit.
- [Первый VM job](https://github.com/chapaayy/Sorter/actions/runs/45499161841/job/138817659061) доказал чистую установку и запуск настоящего systemd: STAGE10_SYSTEMD_INSTALL_OK, шесть healthy контейнеров. Не доказал reboot, потому что до reboot не существовал обязательный файл stage10-boot. Потоковый bash -s допускает чтение оставшихся команд дочерним процессом; воспроизведено локально. Вероятный потребитель stdin — docker compose exec -T. Root-owned QEMU pid/serial требовали sudo.
- e8675d2 исправляет только VM harness и CI scope: выполнение файлов вместо потокового скрипта, явный ready checkpoint, смена boot ID, автоматическое восстановление всех контейнеров, реальная загрузка JPEG через HTTP и контроль SHA-256, проверка TLS и секретов. [VM retest](https://github.com/chapaayy/Sorter/actions/runs/45501539126) ещё выполняется.
- [Нагрузка 1100 фото](https://github.com/chapaayy/Sorter/actions/runs/45499161841/job/138817659578) продолжается на 42e678b. Не отменена и не запущена повторно при идентичном runtime/load коде; scope job подтвердил diff только VM harness. GitHub не выдал журнал незавершённой задачи и артефакт метрик. Время сортировки, RAM, CPU, объём диска, три цикла, часовой TTL и итоговое освобождение резервов пока не доказаны.
- Остаток архитектурной зачистки: внутренние DATA_DIR/RUNS_DIR алиасы внутри storage/app/state (не прежние пути), исторические fixtures и unused imports. Не меняли runtime во время реальной нагрузки.
- PR #22 открыт и не объединён. Main изменился независимо на d6ca808 (экспорт метаданных сторон); исполнитель main не менял, не откатывал, не переносил изменение. Требуется отдельное рассмотрение при будущем слиянии. Действующий VPS не затронут.


## Фактическая перезагрузка и исправление health-проверки
- [VM 138825834636](https://github.com/chapaayy/Sorter/actions/runs/45501539126/job/138825834636): STAGE10_PRISTINE_UBUNTU_OK, STAGE10_SYSTEMD_INSTALL_OK, STAGE10_MODEL_VERIFIED_OK, STAGE10_REPEAT_INSTALL_OK, STAGE10_BOOT_ID_CHANGED. Ubuntu 24.04.5 LTS, Docker 29.10.1, Compose 5.8.0. Boot ID: 532168a8-92ba-4efd-bfa0-e8e212740877 → 90bf5dd2-cf7a-4813-ac87-ebda5badd1cc. Serial console confirms six container scopes, Docker and map-updater.service started automatically. The old probe aborted on missing .State.Health before post-reboot hashes/API update; only PostgreSQL/API have native Healthcheck in compose, other services use HTTPS and heartbeat. Missing health is not proof of healthy or unhealthy service.
- `2d2bbc4` introduces service-specific read-only probe, baseline/reboot/update snapshots, each unit separately, native Health required for postgres/api, real HTTPS, SQL and authenticated status, new and advancing worker identities, same container IDs on reboot. [New VM retest](https://github.com/chapaayy/Sorter/actions/runs/45505109384) is active; no final marker yet. App/runtime/load code identical to 42e678b, original load was not cancelled or duplicated.
- 24b4628 ordinary CI 7/7 (45502987965, 45502997206); 2d2bbc4 ordinary CI 6/7 at checkpoint, Docker pending. Load job 138817659578 still running. No measured report yet; all metrics, 3 cycles, hour TTL, accumulation and release gates remain open.
- Main d6ca808 is owner-authorized independent side metadata export. No revert/merge/port; portable metadata import is separate future task. PR #22 stays draft/open. No existing VPS touched.
- Current documentation rewritten to describe only Storage V2 active paths, branch and policies rather than historical maps. Final source cleanup and measured load acceptance remain open; historical migration files and current API projections must not be deleted merely because their names are old.


## Успешная фактическая Ubuntu VM — 25.11.2026

[GitHub Actions 45505109384, job 138838181284](https://github.com/chapaayy/Sorter/actions/runs/45505109384/job/138838181284), exact SHA 2d2bbc494f8a3c55372bd60f87f7156409b04e1c, SUCCESS. Ordinary [push CI 45505108976](https://github.com/chapaayy/Sorter/actions/runs/45505108976) on the same SHA: 7/7 success.

| Проверка | Измеренное/наблюдённое значение |
|---|---|
| Boot ID до / после | 45fd7183-4c03-498c-83b5-8c97bc07db99 / 09683dfd-7cfc-451f-948f-a2ba2e9310c7 |
| От маркера смены boot ID до полного health подтверждения | 20.827 s (23:00:07.582Z → 23:00:28.409Z) |
| PostgreSQL / API | Native healthy, реальный SQL и authenticated API успешны |
| Caddy | Реальный HTTPS /api/health status=ok; TLS fingerprint unchanged |
| MegaLoc / Thumbnail / Cleanup after reboot | Новые heartbeat instance IDs; advanced between two observations; ages 2.054 / 0.342 / 0.071 s |
| MegaLoc / Thumbnail / Cleanup after API update | Новые instance IDs; advanced; ages 1.111 / 0.601 / 0.139 s |
| Container identities | Все шесть сохранены при reboot; при update обновлены 4 app roles, PostgreSQL/Caddy сохранены |
| systemd | docker.service, map-updater.service, map-log-maintenance.timer enabled/active; без ручного запуска после reboot |
| Persistent data | .env/.env.generated, реально загруженный JPEG, весь SHA-256 model list — OK; DB sentinel and TLS check passed |

Mandatory markers STAGE10_ALL_SERVICES_AUTO_RECOVERED_OK, STAGE10_REAL_REBOOT_OK, STAGE10_REAL_SYSTEMD_API_UPDATE_OK, STAGE10_FRESH_UBUNTU_COMPLETE observed. Earlier missing Health issue is confirmed as wrong harness assumption: only PostgreSQL/API declare native Health, the other four have no native Health property. Functional probes confirmed them, not merely process presence. This closes the fresh install/systemd/reboot/update criterion, **not stage 10**.

Load job [138817659578](https://github.com/chapaayy/Sorter/actions/runs/45499161841/job/138817659578) still in progress; no final report or log yet. Preserve original real workload, no duplicate launched. The last changes are docs-only; no further VM retest for those. Source alias cleanup, measured growth, TTL, three cycles and reserve release still mandatory; do not invent metrics or declare release-ready. Main d6ca808 is explicitly independent per owner; PR #22 not merged.


## Revised stage 10 acceptance (owner decision, 25.11.2026)
- Replace the 1100-photo performance workload with 10 distinct source photos (9 JPEG + one PNG conversion), one MOV video and three complete cycles reusing that corpus; the same source photos are reused as reference fixtures. Actual MegaLoc, upload/resume, codecs, reprocessing, permissions, quota rejection, hardlinks, ZIP CRC/Range, registry snapshots, cleanup and zero reservations remain required.
- Production ZIP TTL stays 3600s; only disposable archives are aged to leave 60s, then the actual cleanup worker must expire them automatically, not early. This is functional acceptance, not a full-hour wall-clock or VPS throughput benchmark.
- The original run is superseded by owner decision; cancellation requires Actions write access. The previous successful VM gate is retained for harness-only edits. Do not mark compact acceptance passed before the new artifact and CI results. Main, PR merge and VPS remain untouched.


## Compact acceptance first result and targeted correction
- Run 45511359785 job 138859658215: all three media cycles and one rerun finished; MegaLoc ~15.2s per sort, ZIP expiry 70/78/64s, all 11 media hardlinked per run, 22 in cycle 2, no registry issues or reserved bytes; post-delete allocated registry bytes identical to baseline (916684800). Final check failed on tracked empty legacy placeholder paths; browser failed before login because /admin is absent from server SPA allowlist. Both issues corrected; browser and storage acceptance must still pass on the new revision.
- Final reference collector removed objects/embeddings, but preview collection had been invoked only before reference history retirement. Now run existing thumbnail GC after reference collection and wait for ZIP lock TTL on aged disposable locks. Production grace/TTL unchanged. Previous host du increased from 968519680 to 985202688 bytes while application registry fell; host growth not attributed without evidence. New snapshots report top-level host directory allocations for diagnosis. Ordinary CI 45511359802 7/7; no new VM gate for this unrelated SPA-route/fixture correction. Main and VPS untouched.


## Second compact acceptance and login navigation fix
- Push CI 45514791803 on 60aba07: 7/7. Real workload 45514791829 / 138871399831: all three cycles, repeated inference, hardlinks, quotas, ZIP cleanup, reference object/embedding/thumbnail cleanup and expired locks passed. Registry allocated bytes after each batch deletion: 916684800 (identical to baseline); final 914612224; zero temporary files, zero registry issues. Host growth from 968634368 to 984875008 bytes is dominated by infrastructure (+18059264 bytes), not application media (app fell from 916967424 to 914956288). Logs grew 192512 bytes. No proof of precise infrastructure subcategory without additional detail.
- Only remaining observed failure in compact run: real Chromium landed on /fo after successful login from /admin. Initial router location can still be '/' before lazy navigation finishes while App checks session. Mount after router.isReady, preserve requested next before login and validate its access role, add owner deep-link and viewer restriction regressions; real browser gate now checks next and actual final URL explicitly. New acceptance remains pending. No repeated Ubuntu VM gate for UI navigation-only change. Main, VPS and PR merge unchanged.
