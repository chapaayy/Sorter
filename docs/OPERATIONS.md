# Эксплуатация MAP Storage V2

[Установка/обновление](DEPLOYMENT.md) · [бэкап](BACKUP_RESTORE.md) · [контракт](STORAGE_V2_FINAL_CATALOG.md).

Сервисы: postgres, caddy, api, worker (одна FIFO сортировка), thumbnail, cleanup. Хост: map-updater.service и map-log-maintenance.timer. Диагностика: `sudo docker compose --env-file .env --env-file .env.generated ps`, `sudo journalctl -u map-updater.service`. Не удаляй файлы напрямую. 

Администрирование → Хранилище: общий объём, категории, временные операции, пользователи, лимиты, сверка и разрешённые операции обслуживания. Устаревший/неполный снимок не основание для удаления. При необходимости запустить фоновую сверку, а не ручной полный обход Ubuntu. Личные квоты и общий временный лимит отключены по умолчанию. Резерв диска действует независимо; при нехватке места API отклоняет новые записи, снижение лимита не удаляет существующие. Обновлятор учитывает собственный минимум свободного места и согласованные резервы. Viewer видит только выданные ему результаты, owner управляет всеми ФО.

Скачивание: ZIP строится по запросу, повторно используется пока действителен, range поддерживается, удаляется cleanup после TTL при отсутствии активных читателей. Удаление партии выполняется через API/UI, не через rm. Общие объекты удаляются лишь после исчезновения зависимостей и grace. Модель и технический кэш имеют разные политики.

Проблемы обновления: проверь журнал updater, состояние active ops, свободное место, образ-кандидат и backup. Не перезапускай установщик поверх незавершённого обновления. При ошибке сохрани данные и диагностический вывод. Не применяй общий Docker prune, не меняй закреплённый storage root.

## Проверка фактического здоровья

На штатном хосте `sudo systemctl is-active docker.service`, `sudo systemctl is-active map-updater.service`, `sudo systemctl is-active map-log-maintenance.timer` проверяются по отдельности. `docker compose ... ps` показывает контейнеры, но не все имеют Docker Healthcheck. PostgreSQL и API обязаны быть native healthy; Caddy проверяется HTTPS `/api/health` с корректным SNI/Host; состояние MegaLoc/thumbnail/cleanup — в authenticated `/api/system/status` (`services.*.alive`, `last_seen`). Heartbeat 10 секунд, alive до 35 секунд. После reboot нужны новые экземпляры heartbeat и его обновление, а не старые строки базы. Не использовать CI VM harness на рабочем VPS.
