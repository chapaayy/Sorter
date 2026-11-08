# Жизненный цикл партии и безопасность данных

## Состояния

`batches.upload_state`: `open` пока партия пуста/есть незавершённые файлы, `ready` когда все ФО завершены, `sealed` после первого запуска MegaLoc (больше нельзя менять ФО без новой версии). При загрузке очередного файла до запуска `ready → open`; состояние вычисляется из реальных записей uploads/jobs, а не из интерфейса.

`batches.delete_state`: `active → deleting → deleted`; при IO/FS ошибке `deleting → delete_failed`, повторный подтверждённый DELETE переводит снова в `deleting`. До удаления партия содержит `upload_state`, `thumbnail_state` (миниатюры создаются асинхронно с этапа 2), `download_confirmed_at`, `confirmed_run_id`, `delete_after_at`. Срок ожидания кодируется датой при `active`, не отдельным состоянием `retention_pending`.

`cleanup_tasks`: `pending → running → completed`; ошибка `failed` с причиной, ручное возобновление возвращает `pending`. Перезапуск контейнера может оставить `running`; worker повторит idempotent процесс. Заявка DELETE возвращается до фактического окончания, состояние доступно через API.

## Ownership

| Источник | Владелец | Удаление batch |
|---|---|---|
| `data/uploads/<batch_id>` | одна партия | **да, все исходники** |
| `data/outputs/<run_id>` | run этой партии | да, все manifests и hardlinks/старые копии |
| `data/runs/<run_id>` | run этой партии | да, события/прогресс |
| `data/incoming/<upload_id>.part` | upload этой партии | да |
| `data/cache/thumbnails` | thumbnail owner/refcount | stage2: shared checksum cache, удаление после grace и отсутствия owners |
| `data/references/SAM-*` | общая библиотека | **НИКОГДА** |
| `data/cache/megaloc/references` | общий reference cache | **НИКОГДА** |
| `Models/**`, users/sessions, Caddy volume | система | **НИКОГДА** |

Удаление вычисляет список run/upload IDs **только из PostgreSQL**, не из произвольного client path, проверяет UUID/run pattern, symlink/path scope. Сначала `deleting` и stop jobs, затем ожидание live `batch_operations` и `running/stopping`; затем idempotent unlink/rmtree **только owned paths**, очистка строк uploads/jobs/confirmations, запись tombstone. Crash после удаления части путей не удаляет чужое. Старые неопубликованные `.megaloc.building` фрагменты автоматически очищаются **только для terminal run** после grace period; работающий MegaLoc не затрагивается. `delete_failed` виден по API; восстановление после устранения причины — повтор DELETE.

## Hard Links

Новые exports: `os.link` exclusive destination, SHA256 + inode/device/size/time проверки, fallback на exclusive copy при EXDEV/несовместимых ФС. Исходник не меняют в пикселях. Удаление одного имени освобождает блоки **только после последнего hardlink и закрытия всех fd**. Старые copied outputs не конвертируются автоматически. Hardlink — не резервная копия.

## Скачивание/срок

Один потоковый ZIP по `GET /api/download/{run_id}`; lease держится до конца/обрыва. HTTP-успех **не подтверждает**, что архив остался на устройстве. Пользователь отдельным `POST .../downloads/confirm` подтверждает только **последний завершённый run** партии. `delete_after_at` назначается в UTC через **2 календарных месяца**. Следующий run сбрасывает прежнее подтверждение/таймер. `POST .../retention/extend` сдвигает срок ещё на 2 календарных месяца. `GET .../retention` сообщает срок и предупреждение за 7 суток. Нет подтверждения → **нет автоматического удаления**.

**Ограничения этапа 1:** миниатюры/общий cache ownership придут в этапе 2; никаких автоматических удалений unconfirmed ФО по нехватке диска; большой ZIP/read-only просмотр не масштабируется на несколько API процессов до полной координации. Проверенный restore test на реальных данных требуется до VPS deployment.

## Превью и незавершённые передачи

`thumbnail_tasks(upload_id)` с ON DELETE CASCADE связана с финализированным upload: `queued → running → ready`, ошибка `running → queued` до 3 попыток, затем `failed`, ручной retry. Рабочие входные оригиналы не редактируются, WebP создаётся отдельно `data/cache/thumbnails/v1/<prefix>/<checksum>.webp` размером 480px long edge/q78. Превью по checksum разделяется между разными ФО партиями и общими Образцами; cache GC удаляет физический файл только после исчезновения **всех** финализированных checksum owners и 24h grace. Удаление партии каскадно удаляет её очередь preview, не global SAM cache.

Временные `incoming/<upload_uuid>.part` с `finalized=false` удаляются отдельно после 30 дней без активности, без активной batch lease, jobs или recent mtime. Для уже существующих исторических uploads миграция создаёт задания preview, не двигает оригиналы. Новый run не кэширует FO embeddings.


## Этап 2: экспериментальные XFeat-результаты

Новые файлы внутри `PhotoSorter/data/outputs/RUN_ID/screen_search` удаляются
общим batch cleanup, который уже удаляет целиком `outputs/RUN_ID`.
Никакой отдельный ZIP или срок хранения не создан.
`PhotoSorter/data/cache/xfeat/references/*.npz` хранит отдельные признаки
с ключом версии и SHA исходного Образца; при изменении разметки прежние
признаки не используются. Автоматическая очистка кэша, безопасная относительно
зафиксированных снимков FIFO, будет финализирована на этапе 4.
