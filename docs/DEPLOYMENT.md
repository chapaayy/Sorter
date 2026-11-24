# MAP Storage V2 — установка и обновление

**Ветка:** `feature/storage-architecture-v2`. Только новый VPS, не миграция старой установки. Статус реальной приёмки: [отчёт](STORAGE_V2_FINAL_REPORT.md).

## Чистая установка

Ubuntu 24.04 LTS x86-64; рекомендуется 8 vCPU, 24 ГиБ RAM, 200 ГиБ SSD для сборки образов, модели и данных. Это ориентир, не измеренный минимум. Нужны sudo/root, пустой путь /opt/Sorter, исходящий HTTPS к репозиториям, DNS A (и корректная AAAA, если есть IPv6), входящие TCP 80/443, необязательно UDP 443. Caddy получает сертификаты автоматически при доступном публичном домене.

```bash
sudo bash -c 'set -e; apt-get update; apt-get install -y git ca-certificates; git clone --single-branch --branch feature/storage-architecture-v2 https://github.com/chapaayy/Sorter.git /opt/Sorter; cd /opt/Sorter; bash install.sh --configure'
```

Введи домен без схемы и пароль admin (16–256 символов; без одинарной кавычки, обратного слеша и управляющих символов). Пароль вводится скрыто, не в аргументах команды. Создаётся .env с правами 0600; PostgreSQL secret и закреплённый storage root генерируются в .env.generated, также 0600. Docker Engine, Compose v2 и Python устанавливаются при отсутствии, создаются управляемые каталоги, собирается MAP, стартуют PostgreSQL, Caddy, API, worker, thumbnail, cleanup. На штатной Ubuntu установщик регистрирует map-updater.service и map-log-maintenance.timer. Не редактируй сгенерированные секреты. Для localhost используется тестовый TLS, не проверка публичного ACME.

После входа под admin в администрировании запусти загрузку настоящей MegaLoc и дождись готовности. Модель не загружается автоматически при каждой установке/обновлении. Повторная установка: `cd /opt/Sorter && sudo bash install.sh --deploy`; `--configure` намеренно не перезаписывает реквизиты. 

## Обновление

В администрировании открой обновления, проверь наличие новой версии и запусти обновление. Updater закреплён на feature/storage-architecture-v2; проверяет доступное место, блокирует новые записи, дожидается активных операций, делает резервную копию БД и конфигурации, собирает и проверяет кандидата. Сбой не является основанием удалять данные. Перед обновлением сделай независимую [полную копию](BACKUP_RESTORE.md). Не используй git reset --hard на рабочем сервере, docker system prune --volumes или ручное удаление storage.

## Проверка

```bash
cd /opt/Sorter
sudo bash install.sh --check
sudo systemctl status map-updater.service map-log-maintenance.timer --no-pager
sudo docker compose --env-file .env --env-file .env.generated ps
```

Установщик автоматически вычисляет допустимые CPU worker, оставляя один CPU сайту при возможности. Дополнительные параметры (BBR, CPU, storage root) необязательны; не меняй root существующей установки. Для чистой установки достаточно домена и пароля. Статусы CI и обязательные незакрытые критерии описаны в итоговом отчёте.
