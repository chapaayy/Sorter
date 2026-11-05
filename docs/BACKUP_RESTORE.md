# Консистентный backup/restore (план перед VPS rollout)

**В этапе 1 в реальном VPS backup и restore не выполнялись: доступ и разрешение на production отсутствуют.** Перед активацией миграций/cleanup оператор должен получить проверенный снимок и продемонстрировать восстановление на отдельном стенде.

1. Приостановить приём новых upload/run и убедиться, что активные дисковые записи завершились; обеспечить согласованность снимка каталога `PhotoSorter/data/` с PostgreSQL. Простой `pg_dump` при одновременно меняющихся файлах не гарантирует согласованный filesystem state.
2. Сохранить в защищённое **другое хранилище**: `pg_dump --format=custom` соответствующей БД; `PhotoSorter/data/references/`, `uploads/`, `outputs/`, `runs/`, `incoming/` и service cache по политике; `.env.generated` с правами 0600; модельные веса `Models/models/` и информацию о version/code SHA.
3. Восстановить копии на **отдельный пустой тестовый VPS/volume**: сначала секреты и файлы с правильным UID, затем `pg_restore` в новую PostgreSQL DB, затем контейнеры тестового приложения. Никогда не использовать production тома для restore-test.
4. Проверить count/size/checksum uploads/refs, индекс jobs/run/manifest, старый/новый ZIP, авторизацию, модель и безопасное удаление **созданной специально тестовой партии**.
5. Записать даты backup/restore, исходный commit SHA, результат checksum smoke test и точку возврата.

Отсутствие offsite backup означает отсутствие проверенной аварийной защиты. Hard Links и второй путь в `outputs/` не спасают при повреждении диска. Никаких команд `down -v`.

## Дополнительный stage2 backup scope

В резервную копию PostgreSQL входят `thumbnail_tasks`, `uploads.updated_at`, новые jobs timestamps и indexes. `data/cache/thumbnails/v1/` — пересчитываемый WebP cache, но для точного восстановления состояния очереди разумно снимать его согласованно с БД. Общий MegaLoc reference embedding cache сохранять отдельно, не трактовать thumbnails как резерв ФО. Во время snapshot приостановить thumbnail/cleanup/worker и завершить pending uploads. Реальный restore в этой беседе не проводился.
