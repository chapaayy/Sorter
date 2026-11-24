# MAP — Match, Assign, Package

Сортировка фотоотчётов наружной рекламы по конструкциям: единый Vue 3 интерфейс, FastAPI, PostgreSQL, MegaLoc CPU, Docker Compose и HTTPS через Caddy.

Эта ветка содержит Storage V2. **Статус финальной приёмки — в [отчёте](docs/STORAGE_V2_FINAL_REPORT.md)**. Не подменяет текущий production и не мигрирует старые данные.

## Установка на новый VPS

```bash
sudo bash -c 'set -e; apt-get update; apt-get install -y git ca-certificates; git clone --single-branch --branch feature/storage-architecture-v2 https://github.com/chapaayy/Sorter.git /opt/Sorter; cd /opt/Sorter; bash install.sh --configure'
```

Подготовь DNS домена и доступные порты TCP 80/443. Введи домен и пароль администратора в интерактивные поля. После входа как admin загрузи MegaLoc через администрирование. Подробнее: [установка и обновление](docs/DEPLOYMENT.md).

## Архитектура

Единый управляемый корень `/opt/Sorter/storage` (по умолчанию). Оригиналы, подготовленные медиа, результаты, общие образцы, миниатюры, эмбеддинги, модель, временные операции, PostgreSQL и сертификаты Caddy разделены по назначению. PostgreSQL хранит очередь FIFO, права, связи объектов, реестр места и квоты. ZIP создаётся по запросу, по умолчанию живёт час. Hardlinks учитываются по физическому объекту. Личные квоты и ограничение временного пула по умолчанию выключены; физическая защита диска включена всегда.

- [Контракт путей и правила каждой категории](docs/STORAGE_V2_FINAL_CATALOG.md)
- [Архитектура Storage V2](docs/STORAGE_ARCHITECTURE_V2.md)
- [Резервное копирование и восстановление](docs/BACKUP_RESTORE.md)
- [Эксплуатация](docs/OPERATIONS.md)
- [Жизненный цикл](docs/DATA_LIFECYCLE.md)
- [Прогресс и фактические проверки](docs/STORAGE_V2_PROGRESS.md)

Исторические документы ранних этапов не являются инструкцией для установки V2.
