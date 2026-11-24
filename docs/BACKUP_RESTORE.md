# Резервное копирование и восстановление Storage V2

Полная копия не равна локальной копии обновлятора. Updater сохраняет ограниченные служебные копии БД/конфигурации; оператору нужен независимый защищённый носитель для пользовательских файлов, модели и TLS. Инструмент `PhotoSorter/tools/maintenance/snapshot.py` поддерживает capture, verify и restore-test с manifest и SHA-256 каждого файла/архива/дампа. Hardlinks сохраняются; опасные ссылки и выход за корень отклоняются. 

## Согласованная копия (root)

Останови приём задач, дождись завершения активных операций; проверь отсутствие активного обновления. Пример для обычного корня, заранее подключённого независимого носителя /mnt/map-backups и свободного имени снимка:

```bash
sudo -i
cd /opt/Sorter
systemctl stop map-log-maintenance.timer map-updater.service
docker compose --env-file .env --env-file .env.generated stop caddy api worker thumbnail cleanup
# PostgreSQL остаётся запущенным.
MAP_SNAPSHOT_COMPOSE_PG=1 python3 PhotoSorter/tools/maintenance/snapshot.py capture \
  --root /opt/Sorter --destination /mnt/map-backups/map-2026-11-25 \
  --database-url postgresql://sorter:local-transport@postgres/sorter --ack-writers-stopped
python3 PhotoSorter/tools/maintenance/snapshot.py verify --archive /mnt/map-backups/map-2026-11-25
docker compose --env-file .env --env-file .env.generated up -d
systemctl start map-updater.service map-log-maintenance.timer
```

local-transport — не пароль пользователя: в специальном режиме MAP_SNAPSHOT_COMPOSE_PG=1 dump/restore выполняется через Docker exec в локальном PostgreSQL. Не публикуй .env, .env.generated, приватные TLS-ключи, архив или дамп. Включены постоянное app-хранилище, незавершённые передачи, модель, эмбеддинги, Caddy data/config, настройки и логический дамп PostgreSQL. Исключены ZIP, scratch, незавершённые скачивания модели, transcoding, frames, processing, логи и служебные рабочие копии. Не копируется живой PGDATA. Если capture/verify завершается ошибкой, снимок не считать годным; возобновить сервисы после устранения проблемы.

## Проверка восстановления

Только на отдельном изолированном стенде с PostgreSQL и пустой тестовой БД, не поверх production. Пример с Compose-транспортом на таком стенде:

```bash
sudo -i
cd /opt/Sorter
docker compose --env-file .env --env-file .env.generated exec -T postgres createdb -U sorter sorter_restore_manual
mkdir -p /mnt/map-restore-test
printf 'STAGING_ONLY\n' > /mnt/map-restore-test/.photosorter-staging-only
MAP_SNAPSHOT_COMPOSE_PG=1 python3 PhotoSorter/tools/maintenance/snapshot.py restore-test \
  --archive /mnt/map-backups/map-2026-11-25 --destination /mnt/map-restore-test/restored \
  --database-url postgresql://sorter:local-transport@postgres/sorter_restore_manual --confirm-staging
```

Путь назначения не должен существовать, тестовая база должна быть пустой и называться sorter_restore_*. Проверить состав и хеши, SQL-связи и записи, hardlinks, запуск Caddy с восстановленным TLS, доступность модели и совпадение эмбеддингов. После проверки только оператор удаляет тестовое окружение. Этот инструмент намеренно не переключает боевую БД или работающий сайт: автоматический production failover не реализован. При потере VPS требуется отдельная изолированная процедура развёртывания с восстановленными данными и секретами; перенос путей и запуск должны быть проверены до переключения DNS. Не использовать старые инструкции для PhotoSorter/data/Models.
