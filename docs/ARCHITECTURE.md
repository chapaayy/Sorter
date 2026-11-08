# Архитектура PhotoSorter (beta)

Исходное приложение было одним FastAPI `main.py` и modules `uploads/jobs/database`. После этапа 1 `server/main.py` выполняет только сборку приложения, middleware авторизации и lifecycle. `server/api/routes/*` имеют HTTP-контракты, `server/services/*` владеют batch/retention/cleanup/storage use cases, `server/storage/*` — проверками файловой системы, `server/db/*` — SQL-миграциями.

**Не изменено:** `app/recognition` (математика, вектора, группировка, назначение SAM), PostgreSQL-сессии, Caddy, единый Vue SPA на `/`, direct PUT/PATCH и full ZIP на zipstream-ng. `server/jobs.py` и `server/uploads.py` пока удерживают часть legacy бизнес-логики; миграция их оставшейся части должна быть отдельной тестируемой декомпозицией, не косметической заменой.

**Данные:** `Models/` отдельно от `PhotoSorter/`, файлы в постоянном bind mount, DB и HTTPS state — в Docker volumes. Образцы и их embedding cache не owned by batch. Результаты нового run имеют такой же manifest interface, а записываются во временный `.megaloc.building` каталог и атомарно публикуются в `outputs/<run_id>/megaloc/`.

**Конкурентность:** одна API-реплика (в upload используется process-local asyncio lock); Worker обеспечивает последовательную обработку в текущем Compose. `batch_operations` защищает реальные upload/ZIP потоки; delete-state блокирует новые операции, run enqueue и finish. Очистка запускается отдельным low-resource worker и ждёт прекращения jobs и live IO. Не масштабировать API/Worker, пока не введены распределённые upload locks и доказанная координация очереди.

Полные потоки перечислены в [PROJECT_MAP](../PROJECT_MAP.md), правила сохранности в [DATA_LIFECYCLE](DATA_LIFECYCLE.md).

## Очереди, галереи и превью

`server/main.py` остаётся сборщиком маршрутов. `server/api/routes/{thumbnails,references,originals,system}.py` содержит только HTTP-контракты; `server/services/{thumbnails,result_pages,disk_guard,temp_cleanup,thumbnail_gc}.py` — предметные операции; `server/db/repositories/{queue,pagination}.py` — SQL FIFO/keyset; `server/storage/thumbnail_cache.py` — кэш файлов без бизнес-логики.

`server/workers/thumbnail.py` выполняет обработку WebP вне upload HTTP, атомарно; отдельный Worker MegaLoc ограничен 1 running через session-level advisory leader lock плюс transaction gate. Новые `manifest.rows.jsonl` создаются параллельно старому неизменному manifest.json/CSV/ZIP, только для новых результатов. `app/logging/events.py` пишет ротационные JSONL и читает курсорно; Docker stdout тоже ротируется. `api/system` отображает измеренные времена API, не выдаёт гипотезы за факты.

**Ограничение:** горизонтальное масштабирование API пока требует распределённых блокировок загрузки; в Docker Compose предусматривается один API и один MegaLoc Worker.

## Единственный Vue SPA

`frontend/static` удалён из main. `frontend/src` построен на Vue3/Pinia/Vue Router/TypeScript; в runtime Python FastAPI отдаёт собранный Vite `dist` на `/`, SPA deep links `/fo/*` и другие известные разделы. `/assets/*` защищён от path traversal и symlink выхода за dist. Сборка Node24 выполняется только в Docker builder. Всё state сессии находится в httpOnly cookie, frontend хранит только theme и idempotent upload identity (не фото/пароли).

ФО/Образцы/Обработка/Результаты/Логи/Настройки имеют отдельные папки features; REST API клиенты и composables отделены от компонентов. Backend содержит небольшой `services/references.py` для SAM rename/delete/cache, расширяет list batch counters, tail log API и ручную очистку только ownerless thumbnail cache. Ядро `app/recognition/` не изменялось.

## Мониторинг и восстановление

- Между job очередью и процессной доступностью теперь независимая сущность `service_heartbeats`. Single-process API выставляет `services` для monitoring, а фоновые процессы пишут heartbeat отдельными daemon threads. Отказ DB отражается как ошибка, не подменяется фиктивным `alive`.
- Snapshot и restored bytes выполняют независимые операции с project/data + Models cache/models. PostgreSQL custom dump сохраняется отдельно от файлового tar, копия считается **согласованной только если оператор остановил все writers**. Manifest backup имеет SHA, tar hardlink references, БД после восстановления проверяется на отдельной staging DB.
- Отдельные инструменты `compare_baseline.py`, `staging_probe.py` обслуживают измерения и приёмку, не влияют на inference path. Production rollback и acceptance — [ROLLOUT](ROLLOUT.md).


## Один runtime

Очередь только `work_queue`; FIFO claim при запуске Worker, никакого
выбора старой реализации. Образцы только staging + immutable published
members. В `uploads` строки вида `reference` — индекс отображения галереи,
не самостоятельный путь загрузки. См. `REFERENCE_PIPELINE.md`.

## Экранная разметка: этап 1 (ветка feature/ad-recognition)

`reference_screens` описывает физический рекламный экран и его конструкцию.
`reference_screen_annotations` хранит привязки этого экрана к отдельным
опубликованным Образцам, четыре угла после EXIF, толщину полосы в пикселях,
SHA-256 исходного файла и растущую версию. PostgreSQL FK удаляют разметку
при удалении исходного Образца; другие ракурсы того же экрана сохраняются.

`services/screen_geometry.py` проверяет выпуклость, невыраженность,
площадь, границы и толщину полосы; `services/screen_annotations.py`
разрешает только опубликованные Образцы своей конструкции и безопасные
пути в `data/references`, версии защищены от устаревшей перезаписи.
Модуль не читает очерёдность FIFO и пока не влияет на MegaLoc или ZIP.

Frontend запускает `ScreenAnnotationEditor.vue` внутри действующей
галереи Образцов; SVG переносит координаты через фактическую матрицу
экрана, браузерные размеры сверяются с EXIF-ориентированными оригиналом.
Полоса пока только визуализируется; XFeat подключается на этапе 2.


## Экспериментальный поиск экранов (этап 2)

**Без второй очереди:** оператор на новом VPS запускает `app.screen_detection.cli`
на опубликованном MegaLoc run после завершения ZIP. Сервис проверяет
`jobs.status`, исходный файл под каталогом своей партии, и берёт разметки
строго по `assigned_sam`. Не определённая конструкция и отсутствие разметки
дают диагностические статусы. ML вынесен в `app/screen_detection`; HTTP
только читает результаты через отдельный router. Файлы сохраняются в том
же `outputs/<run_id>`, а не в новом постоянном root/volume.

Официальные XFeat-веса и исходники закреплены SHA Git blob. Веса —
`Models/models/xfeat/xfeat.pt`, исходники загрузчика —
`Models/cache/xfeat/official/modules/`. Локальная проверка обязательна
перед каждым созданием модели; загрузка только явной командой.

Поиск: EXIF → RGB → уменьшение без изменения пропорций → sparse XFeat →
фильтрация опорных точек вдоль 4 сторон полосы Образца → MNN →
OpenCV USAC_MAGSAC/RANSAC → консервативные проверки inliers, разных
сторон, ошибки и проекции → четырёхугольник на ФО. Вырезается внешний
прямоугольник из исходных ориентированных пикселей, без выравнивания.
Результаты хранят версии разметок и параметры диагностики. Флагов
достоверности в процентах нет. Дальнейшая интеграция в единую FIFO,
полный ZIP, OCR и качество — в последующих этапах.

Ручной длительный анализ удерживает `batch_operations` lease, периодически
обновляет heartbeat и освобождает её при завершении/ошибке. Это существующий
механизм защиты файлов при удалении партии, **не** новая очередь.
`--start-index` и `--limit` позволяют продолжать по частям без повторного
считывания предыдущих изображений; одиночные ошибки ФО сохраняются отдельно.


## Этап 3: модуль классификации рекламного макета

Библиотека исходных рекламных макетов не зависит от конструкций. Оригинал
(20 МиБ, только JPEG/PNG/WEBP) сохраняется неизменным, SHA уникален,
метаданные с оптимистической версией — в PostgreSQL. При обновлении имени
или контрольного текста оригинал и признаковый кэш не пересчитываются.

Ручной CPU анализ завершённого MegaLoc run читает **только** опубликованные
этапом 2 XFeat-контуры `found` и их исходные `crop_box`. Пиксели за пределами
полигональной области маскируются. DINOv2 ViT-S/14 формирует единообразные
384D L2 embeddings макетов и cropped-экранов, ранжирует по cosine-similarity,
использует экспериментальные пороги `MIN_SIMILARITY` и `MIN_MARGIN`.
Признаки макетов сохраняются отдельно по `sha256(original)+signature(model)`.
PP-OCRv5 распознаёт восточнославянский текст в сопоставляемом экране;
если контрольный текст не указан вручную, сравнивает текст оригинального
макета и ФО. Статус OCR — подтверждение/сомнение/не прочитано/недоступно,
**никогда** смена `candidate_id`. Нет переназначения конструкции и ZIP.

Результаты находятся в каталоге outputs исходного run. Ручной анализ
использует существующую `batch_operations` lease для защиты от удаления.
Автоматическая очередь, версионирование снимков на момент claim, качество
и ZIP-интеграция — задачи этапа 4.


## Stage 4 — opt-in single FIFO (supersedes earlier «stage 4 pending» notes)

`processing_settings.ad_pipeline_enabled` false by default. Current
Mono-Worker/FIFO claim is extended to capture immutable annotations and
layout metadata **after** MegaLoc pins its reference version, in the
same SQL transaction. The reference source path is taken from that
version's immutable member, not the mutable reference gallery.
Layout deletions are blocked while an integrated run is active;
metadata edits do not retroactively change its snapshot.

`ServerJob.finalize_results` executes `ad_pipeline.process` and only
then `archive_pipeline.build_for_job`. Filesystem stages remain
subdirectories of `outputs/RUN_ID`; each has a version signature.
Stages run on the existing CPU thread budget; no separate scheduler,
worker or background task is introduced. A systemic model error prevents
ZIP and completion. Per-photo failures yield explicit diagnostics, not
fabricated recognised ads.

Full ZIP is immutable for the run: all MegaLoc originals remain;
`Best_by_layout` and `Review_required` contain best originals
by screen/layout; `Ad_recognition/summary.json` includes version
and quality metadata. `archives.prepare` still performs atomic
publish and CRC verification. `archive_pipeline.selections` reads
the saved Stage 4 result on first build AND ZIP-only recovery. There
is never inference on download or archive retry.

`quality.py` uses only masked ROI: Laplacian sharpness, clipped black/
white values, specular-glare fraction, and pixel coverage of the screen.
It yields a 0–100 *relative heuristic*, not a confidence score.
`best.py` groups by (`sam`,`screen_id`,`candidate_id`), prioritises
OCR-confirmed matched ads, then relative quality, then the earlier photo.
DINOv2 uncertain/no_match never generates a best candidate.
