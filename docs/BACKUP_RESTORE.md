# Бэкап и восстановление PhotoSorter

**Перед любым обновлением или сбросом бета-сервера:** согласованный бэкап и его восстановление нужно проверить на отдельном стенде. Наличие файла архива на том же VPS не равно проверенной защите.

1. Приостановить приём новых upload/run и убедиться, что активные дисковые записи завершились; обеспечить согласованность снимка каталога `PhotoSorter/data/` с PostgreSQL. Простой `pg_dump` при одновременно меняющихся файлах не гарантирует согласованный filesystem state.
2. Сохранить в защищённое **другое хранилище**: `pg_dump --format=custom` соответствующей БД; `PhotoSorter/data/references/`, `uploads/`, `outputs/`, `runs/`, `incoming/` и service cache по политике; `.env.generated` с правами 0600; модельные веса `Models/models/` и информацию о version/code SHA.
3. Восстановить копии на **отдельный пустой тестовый VPS/volume**: сначала секреты и файлы с правильным UID, затем `pg_restore` в новую PostgreSQL DB, затем контейнеры тестового приложения. Никогда не использовать production тома для restore-test.
4. Проверить count/size/checksum uploads/refs, индекс jobs/run/manifest, старый/новый ZIP, авторизацию, модель и безопасное удаление **созданной специально тестовой партии**.
5. Записать даты backup/restore, исходный commit SHA, результат checksum smoke test и точку возврата.

Отсутствие offsite backup означает отсутствие проверенной аварийной защиты. Hard Links и второй путь в `outputs/` не спасают при повреждении диска. Никаких команд `down -v`.

## Дополнительные данные PostgreSQL и WebP

В резервную копию PostgreSQL входят `thumbnail_tasks`, `uploads.updated_at`, новые jobs timestamps и indexes. `data/cache/thumbnails/v1/` — пересчитываемый WebP cache, но для точного восстановления состояния очереди разумно снимать его согласованно с БД. Общий MegaLoc reference embedding cache сохранять отдельно, не трактовать thumbnails как резерв ФО. Во время snapshot приостановить thumbnail/cleanup/worker и завершить pending uploads. Реальное offsite восстановление нужно проверять отдельно от CI.

Vue UI — клиент существующих серверных состояний. Он не создает новую резервную систему, а показывает предупреждение, если проверенная внешняя копия неизвестна. Сохранение `package-lock.json` и dist assets **не заменяет** snapshot PostgreSQL+data+Models при реальном обновлении. Rename SAM изменяет пути Образцов — перед production тестом понадобится согласованная копия данных и проверка зависимостей старых manifests.

## Утилита snapshot и границы CI

`PhotoSorter/tools/maintenance/snapshot.py`: команды `capture`/`verify`/`restore-test`. Перед backup **оператор выключает всех writers**, после чего явно передаёт `--ack-writers-stopped`. Snapshot включает `PhotoSorter/data`, `Models/models`, `Models/cache`, конфигурацию/секреты, `pg_dump` custom format. SHA-256 каждой записи и всего tar/dump; повторные inode оформляются tar Hard Link. Архив создаётся в другом каталоге, владеет 0700, ни один исходный файл не меняется.

Restore требует `--confirm-staging`, **новый каталог** и marker `.photosorter-staging-only` со значением `STAGING_ONLY` в его родителе. БД должна существовать, быть пустой и называться `sorter_restore_*`; при некорректном/подменённом tar никакой распаковки до `verify()`.

CI `ci_restore_drill.py` действительно вызывает `pg_dump` и `pg_restore` с PostgreSQL17 на двух disposable базах и проверяет SHA файлов, запись БД и inode. **Это не снимок VPS**. Настоящая резервная копия должна быть зашифрована offsite (внутри находятся пароли `.env.generated` и фотографии). Caddy Docker volume с TLS private keys нужно отдельно копировать и восстанавливать. Без offsite restore-test не давать согласие на production rollout. Команды: [STAGE4_ROLLOUT](ROLLOUT.md).

## Новые данные Stage 4

Согласованная внешняя копия должна включать новые PostgreSQL таблицы `reference_library_versions`, `reference_version_members`, `reference_library_events`, `library_notice_cursors`, `fo_library_upload_receipts`, `reference_import_*`, `reference_preparation_*`, `work_queue`; из `PhotoSorter/data` сохранять `reference_staging/`, `reference_objects/`, кэш эмбеддингов, исходники и outputs. Файлы staging/immutable и курсоры должны быть восстановлены вместе с PostgreSQL, а не выборочно. Перед переносом выполнить offsite verify + restore-test на пустой отдельной DB и проверить Caddy TLS volumes. Не использовать `docker compose down -v`.

В Postgres 17 snapshot входит `fo_library_upload_receipts` и миграционная запись `library_notice_cursors` для ранее завершённых ФО (schema `0017`). При восстановлении на другом сервере нельзя сбрасывать cursor: иначе следующая публикация может создать ложное/пропущенное предупреждение.
