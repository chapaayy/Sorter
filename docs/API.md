# API — актуальная поверхность

База `/api`. Все маршруты кроме `GET /api/health` и `POST /api/auth/login` требуют существующую cookie session; mutating endpoints защищены Origin/Sec-Fetch-Site. JSON timestamps — UTC/ISO, photo paths наружу не выдаются новыми batch list endpoints.

## Сохранившиеся endpoints

| HTTP | Путь | Контракт |
|---|---|---|
| GET | `/health` | версия/status |
| POST/POST/GET | `/auth/login`, `/auth/logout`, `/auth/me` | sessions (не менялись) |
| POST | `/uploads` | init kind/filename/size/batch_id/sam/address/checksum; optional `client_upload_id` (UUID) makes POST idempotent after lost network response |
| GET/PATCH | `/uploads/{upload_id}` | offsets и докачка |
| PUT | `/uploads/direct/{upload_id}` | быстрый single request, fallback PATCH |
| POST | `/uploads/{upload_id}/finish` | final SHA/Pillow validation |
| GET | `/references`, `/references/files` | список конструкций (`sam`, `display_name`, `address`, `city_code`, `construction_number`, `photos`) и файлов |
| DELETE | `/references/files/{reference_id}` | защищённое удаление общего образца |
| GET/POST | `/runs` | история / enqueue (всё ещё одна текущая job; очередь этапа 2) |
| GET | `/runs/{run_id}` | progress |
| POST | `/runs/{run_id}/stop` | остановка |
| GET/POST | `/models`, `/models/megaloc/download` | одна модель |
| GET | `/results/{run_id}`, `/results/{run_id}/megaloc` | run/manifest/score |
| GET | `/images/{run_id}/megaloc/{index}` | image query/copy/reference |
| GET | `/download/{run_id}?sam=SAM-0045` | ZIP поток всей сортировки либо одного SAM |
| GET | `/logs/{run_id}` | run события |

## Новые endpoints этапа 1

| HTTP | Путь | Ввод/ответ |
|---|---|---|
| POST | `/batches` | optional `{display_name}`; `{batch_id,display_name}` |
| GET | `/batches?limit=100&offset=0` | `{batches,total}` (limit 1–200) |
| GET | `/batches/{id}` | `batch_id,photos,size_bytes,pending,runs,display_name,*_state,*_at` + `latest_run`, `last_result_run_id` |
| GET | `/batches/{id}/pending` | Незафиксированные загрузки ФО: UUID, имя, фактический offset на диске, размер, наличие `.part`, `can_finalize`, SHA-256 всей полученной части (только для незавершённого файла) для безопасной ручной докачки |
| PUT | `/batches/{id}/upload-manifest` | Для новой пустой партии: `{files:[{upload_id: UUID, relative_path, filename, size}], auto_process?:bool, grouping_threshold?:0.50…0.99}` (1–20000 фото). Указанные auto-параметры фиксируются **только при первой регистрации**; идемпотентный повтор с тем же манифестом не включает заново отменённый автозапуск. Старые партии с уже существующими uploads не изменяются. |
| GET | `/batches/{id}/upload-manifest` | `{state:legacy/waiting/complete, expected, finalized, missing, pending, files:[{upload_id,relative_path,filename,size,state,received}]}`. `state=legacy` означает отсутствие подтверждённого манифеста, а НЕ автоматически завершённую загрузку. |
| PATCH | `/batches/{id}` | `{display_name}`, 1–120 символов |
| GET | `/batches/{id}/photos` | пагинация метаданных ФО |
| DELETE | `/batches/{id}/photos/{photo_id}` | только пока нет run |
| DELETE | `/batches/{id}` | 202 `{batch_id,state: deleting/deleted}`; **всё принадлежащее партии** |
| GET | `/batches/{id}/deletion` | `delete_state`, task progress/error |
| POST | `/batches/{id}/downloads/confirm` | `{run_id}`, лишь опубликованный полный результат |
| POST | `/batches/{id}/retention/extend` | новая дата, +2 календарных месяца |
| GET | `/batches/{id}/retention` | даты и предупреждение за 7 дней |
| GET | `/storage/usage` | mount total/used/available, inode-counted categories |

## Этап 4 — панель обработки MegaLoc

Для независимого малонагруженного мониторинга UI запрашивает `GET /runs?scope=active&limit=25` и `GET /system/status` раз в 4 секунды. `GET /runs?scope=history&limit=30&offset=N` — постраничная история, обновляется реже. Модель и серверные настройки читаются через существующие `GET /models` и `GET /processing-settings`, изменения в настройках — через прежний `PATCH /processing-settings`. Статус Worker только из `system/status.services.megaloc`; отсутствие heartbeat не приравнивается к успешной обработке. `POST /runs/{id}/stop` требует UI-подтверждения, для `queued` останавливает до начала, для `running` запрашивает остановку.

Раздел `/processing` удалён: запуск из `/fo`, подробности в `/queue/runs/:runId`, история из вкладки «Очередь». `POST /runs` и повторная сортировка по-прежнему поддерживаются backend, кнопки запуска находятся в `/fo`. Все результаты и история остаются доступны. Реальные сетевые/ВПС сценарии — `docs/STAGE4_ACCEPTANCE.md`.

## Этап 3 — статусы MegaLoc внутри ФО

| HTTP | Путь | Контракт |
|---|---|---|
| GET | `/batches?limit=&offset=` | Каждый batch имеет `latest_run` (или null) с актуальным `jobs.status`, `queue_position`, `progress`, `grouping_threshold` и датами; также `last_result_run_id` — последний завершённый `completed`/`completed_with_errors`, **независимо** от статуса более нового запуска. Никаких FS paths в этих полях. |
| GET | `/batches/{id}` | Та же модель статуса и предыдущих результатов для галереи партии |
| GET | `/batches/{id}/runs?limit=20&offset=0` | Изолированная по партии история: `{runs,total}`, limit 1–100, offset ≥0. Текущий `status` всегда из PostgreSQL, не из устаревшего JSON snapshot; JSON progress только измеренный. Без путей к файлам. |

Действия интерфейса используют существующие `POST /runs` и `POST /runs/{id}/stop`; «Убрать из очереди» переводит queued → stopped, но не удаляет запись, результаты и оригиналы. `thumbnail_state=ready` не означает MegaLoc completed. Только `completed` показывается зелёным; `completed_with_errors`/`failed` — ошибки, `stopped`/`interrupted` — нейтральные. Если повторная обработка завершилась неудачей, прежний `last_result_run_id` сохраняет переход к последнему результату.

## Этап 2 — серверный автоматический MegaLoc

| HTTP | Путь | Контракт |
|---|---|---|
| GET | `/processing-settings` | `{auto_process_new_batches:false,grouping_threshold:0.50,model:"megaloc"}` по умолчанию; хранится на сервере |
| PATCH | `/processing-settings` | `{auto_process_new_batches:bool,grouping_threshold:number}`; новые настройки действуют только на новые партии |
| POST | `/batches/{id}/auto-processing/cancel` | Для новой партии с манифестом отменяет ожидание перед enqueue; после создания job → 409, дальше используйте `/runs/{id}/stop` |
| GET | `/batches/{id}` | Доп. поля `auto_process_state`, `auto_process_threshold`, `auto_process_run_id`, `auto_process_error` |
| GET | `/batches/{id}/upload-manifest` | Доп. поля автообработки: state, run_id, error, threshold. Для legacy не означает согласия на автоматический запуск |

Общий default OFF. Никаких авто-заданий для legacy, старых результатов или партии без явного нового opt-in. Фоновый `cleanup` раз в ~30 секунд проверяет `waiting + complete`, оригиналы, SAM и очередь и вызывает общий транзакционный enqueue под advisory lock с `source=automatic` и сохранённым порогом; модель MegaLoc должна быть установлена. `queued` навсегда отмечает факт автоматической постановки даже если job закончился с ошибкой: бесконечных повторов нет. При busy/full ожидает освобождения очереди, при ошибке настройки/отсутствии SAM пишет причину ожидания. `source` может быть `manual` или `automatic` в snapshot задания. Старые HTTP контракты не удалены.

**Инвариант этапа 1:** для новых партий `POST /uploads` принимает только зарегистрированный `client_upload_id`, имя и размер; в `finish` сервер сверяет весь манифест и фиксирует `complete`, только когда подтверждены все оригиналы. `POST /runs` для `waiting` возвращает 422 даже при `pending=0`. Старые партии используют прежнюю семантику.

Ошибки: `401` сессия, `403` Origin, `404` не найден, `409` несовместимое состояние (после run нельзя удалить одну ФО, deleting запрещает upload/run/ZIP), `422` invalid field/threshold. `DELETE batch` фактически выполняет maintenance worker, не блокирует HTTP. Веб-UI будет использовать новые endpoints в этапе 3, до него старые вкладки остаются.

См. [MIGRATION_NOTES](MIGRATION_NOTES.md) и [DATA_LIFECYCLE](DATA_LIFECYCLE.md).

## Этап 2 — новые пути и результаты

| HTTP | Путь | Контракт |
|---|---|---|
| DELETE | `/uploads/{upload_id}` | только unfinished .part, finalized→409; используется для адресной подтверждаемой отмены одного недогруженного ФО |
| GET | `/batches/{id}/gallery?limit=&cursor=` | keyset 1–200, photos/next_cursor, thumbnails и original URLs |
| GET | `/references/{sam}/photos?limit=&cursor=` | keyset SAM gallery |
| GET | `/results/{run_id}/photos?sam=&group=&limit=&cursor=` | постраничные photos с реальными score/group/index |
| GET | `/results/{run_id}/sam` | counts по SAM, в т.ч. Неопределено |
| GET | `/results/{run_id}/groups` | counts по group_id |
| GET | `/thumbnails/{photo_id}` | 200 image/webp, 202 pending, 404 отсутствует |
| GET | `/thumbnails/status/{batch_id}/counts` | фактические total/ready/failed |
| POST | `/thumbnails/{photo_id}/retry` | failed/queued → queued (202) |
| GET | `/photos/{photo_id}/original` | оригинал только по DB UUID, с batch read lease |
| GET | `/runs?limit=&offset=&scope=` | Без `scope` контракт не изменён: все runs + total, очередь с `queue_position`. `scope=active` — только `queued/running/stopping`, `scope=history` — только терминальные статусы. Неверный scope → 422. История и мониторинг используют один API/одну очередь. |
| POST | `/runs` | FIFO 202, максимум 20 queued; 429 full, 409 duplicate active batch |
| GET | `/logs/{run_id}/page?limit=&cursor=` | 1–500, next_cursor; 422 устаревший segment |
| GET | `/logs/{run_id}` | ограниченный совместимый хвост (default 250) |
| GET | `/logs/usage` | bytes/budget |
| GET | `/system/status` | uptime, queue, thumbnail counts, free/reserve, recent p95 API |
| GET | `/storage/usage` | inode-dedup категории + отдельно approx pg_database_size |

**API backwards compatibility:** `GET /results/{run_id}/megaloc` до сих пор возвращает прежний manifest, `GET /download/{run_id}?sam=` стримит ZIP без постоянного файла; POST auth/cookies/Origin остаются. Browser не передаёт filesystem paths. Старые completed runs без `manifest.rows.jsonl` поддерживаются legacy fallback, но могут требовать чтения полного manifest.

**Состояния:** after upload original ready сразу, thumbnail queued/running/ready/failed независимо; `queue_position` появляется только у queued job. После crash running→interrupted; никаких ложных восстановлений промежуточных нейронных embedding. ENOSPC → HTTP 507 для новых загрузок, не удаляет completed файлы.

## Vue и SAM API

| Метод | URI | Назначение |
|---|---|---|
| GET | `/api/references/cache/status` | total/cached по текущей подписи модели, если доступна |
| PATCH | `/api/references/sam/{sam}` | Историческая операция переименования старого `SAM-xxxx`; не применяется к новому ключу |
| DELETE | `/api/references/sam/{sam}` | удалить всю SAM и принадлежащие эталонные фото |
| GET | `/api/logs/{run_id}/page?tail_mode=true` | последние ограниченные события плюс курсор от конца |
| POST | `/api/system/cache/cleanup` | только cache WebP без checksum owner и устаревшие временные файлы |
| GET | `/`, `/fo/:id`, `/references`, `/queue`, `/queue/runs/:runId`, `/results`, `/logs`, `/settings` и другие SPA пути | Единственный Vue bundle, history fallback, только read-only HTML |
| GET | `/assets/*` | Только собранные Vite assets внутри `frontend/dist/assets`, без path traversal |

**Сохранённый API:** `/api/auth/login`, `/api/auth/logout`, streaming ZIP, batch CRUD, очереди и API этапов 1–4. API защищён cookie/Origin middleware; root Vue не ослабляет авторизацию. Если Vue dist отсутствует, `/` и SPA deep links возвращают 503, а `/api/health` продолжает работать. Старые `/v3/` и `/static/*` возвращают 404.

**SAM rename safety:** запрещён при queued/running/stopping MegaLoc и незавершённых загрузках данной SAM. Исторические manifests с исходными путями требуют отдельной проверки/миграции при переименовании библиотеки, прежде чем включать эту функцию на рабочем VPS. Это не изменяет MegaLoc math.

## Строгий массовый импорт конструкций

| Метод | Путь | Контракт |
|---|---|---|
| POST | `/api/references/import/preview` | `{"folders":["SAM 0004 — Гагарина 64"]}` → `entries` (new/existing/адрес/фото), `errors`, `cities`; без записи в БД |
| POST | `/api/uploads` | `kind=reference`, `sam="SAM 0004"`, `address="Гагарина 64"`, filename/size; создание или дополнение без изменения существующего адреса |
| PATCH | `/api/references/constructions/{sam}/address` | `{"address":"Гагарина 64А"}` → новое отображаемое имя без смены идентификатора |
| GET | `/api/references` | Отдаёт новое отображаемое имя и прежние `sam` для старых записей |

Уникальность конструкции: `city_code + construction_number` (строка, ведущие нули сохраняются). Старые `SAM-xxxx` не переименовываются и не принимаются как названия папок при новом массовом импорте. Дубликат фотографии по SHA-256 в одной конструкции не сохраняется второй раз. Неправильный адрес возвращает 409/422; активная MegaLoc блокирует изменения. Миграция `0008_reference_constructions.sql` добавляет каталог конструкций без удаления старых данных. Полные правила: [REFERENCE_IMPORT](REFERENCE_IMPORT.md).

**Предупреждение о ZIP:** `GET /api/download/{run_id}` только начинает поток; отдельный пользовательский `POST /api/batches/{id}/downloads/confirm` требуется после проверки файла. UI не пытается автоматически подтвердить получение архива.

## Здоровье служб и защита API

- `GET /api/system/status`: добавлено поле `services.{megaloc,thumbnail,cleanup}.{alive,last_seen}` на реальном PostgreSQL heartbeat. Это совместимое **добавление**, старые поля сохраняются. Состояние `alive` означает недавно полученный сигнал процесса, не гарантирует быстроту/успешность инференса.
- `POST /api/auth/login`: после повторных неудач может вернуть HTTP 429 (bounded ephemeral throttle) вместо 401; формат cookies и DB-сессий не менялся.
- Upload finalize: изображение свыше 30 млн пикселей HTTP 422, лимит файла 60MB остаётся.
- `GET /api/download/{run_id}`: прежде чем публиковать member архив, проверяет SAM/filename на `../`, слеши, NUL и другие path escapes; формат ZIP и права / leases прежние.
- `PATCH /api/references/sam/{sam}` / `DELETE`: если SAM встретилась в опубликованном историческом manifest, возвращает HTTP 409. Записанные manifests и source References не меняются при отказе.
- Изменение БД: `0007_service_heartbeat.sql` (таблица worker presence), никакие таблицы партий, uploads, MegaLoc scores не переопределены.


## Единый beta pipeline

Очередь ФО и подготовок образцов — только `work_queue.seq`; загрузка образцов всегда доступна через `/api/reference-imports` и сохраняет файлы в `reference_staging`. После полной подготовки публикуется неизменяемая версия библиотеки. Обе версии планировщика и условные флаги переключения удалены. Приёмка — тесты на пустой базе, докачку, FIFO, публикацию и браузеры Chromium/WebKit. Текущая архитектура: [REFERENCE_PIPELINE](REFERENCE_PIPELINE.md).

## Ресурсы новой версии

| Method | URL | Функция |
|---|---|---|
| GET | `/processing-settings/cpu` | Предпочтительные вычислительные потоки MegaLoc и реальный максимум Worker |
| PATCH | `/processing-settings/cpu` | Обновить число потоков для **следующего** задания |
| GET | `/download/{run_id}?sam=...` | Готовый ZIP, `Content-Length`, `Accept-Ranges`, HTTP 206 |
| GET | `/work-queue?scope=history&limit=100` | История обработки ФО и образцов для отдельного режима в «Очереди» |

Не выдавать Docker socket в веб-приложение: лимиты cgroup остаются параметрами Compose.

## Новые endpoints: полный ZIP и настройки

- `POST /api/runs/{id}/archive/retry` — повторная подготовка ZIP без MegaLoc.
- `GET/PATCH /api/system/retention` — `{enabled, value, unit}`, где `unit` это `minutes`, `hours`, `days` или `months`; только для будущих готовых задач.
- `GET/PATCH /api/processing-settings/workloads` — `{mode, fo_threads, reference_threads}`; CPU применяется к следующей задаче.
- `GET /api/download/{id}` — готовый ZIP с Range/206; для старых запусков сохранён совместимый fallback.

`POST /api/batches/{id}/downloads/confirm` оставлен как legacy API. В новом UI подтверждение скачивания больше не требуется.

## Разметка экрана (этап 1, feature/ad-recognition)

Все новые маршруты защищены теми же session-cookie и Origin, что остальные `/api/*`.

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/api/references/{sam}/screens` | Экраны конструкции и их сохранённые разметки |
| GET | `/api/references/{sam}/photos/{reference_id}/screen-metadata` | Размеры оригинала после EXIF, SHA-256 |
| POST | `/api/references/{sam}/screen-annotations` | Создать экран или его разметку на ещё одном Образце |
| PATCH | `/api/references/{sam}/screen-annotations/{id}` | Изменить геометрию с проверкой `version` |
| DELETE | `/api/references/{sam}/screen-annotations/{id}` | Удалить одну разметку |
| DELETE | `/api/references/{sam}/screens/{id}` | Удалить экран и все его ракурсы |

POST: `{reference_id,screen_id:null,screen_name:"Экран 1",corners:[{x,y},...],band_width_px:10}` для нового экрана или `screen_id` существующего экрана без имени. PATCH: `{corners:[{x,y},...],band_width_px:10,version:1}`. Углы идут последовательно по контуру в пикселях EXIF-ориентированного оригинала. Ответ POST/PATCH: `{id,screen_id,version}`. Ошибки `404` при отсутствии фото/экрана, `409` при конфликтах версий/дублировании, `422` при недопустимой геометрии.


## Поиск экранов — read-only API тестового этапа 2

- `GET /api/screen-search/model`: готовность проверенных локальных XFeat-файлов.
- `GET /api/screen-search/runs/{run_id}/photos/{index}`: сохранённый результат
  со `status`, `reason`, `image_width/height` и `screens[]`. Каждый экран
  содержит `screen_id`, имя, `annotation_version`, `reference_width/reference_height`, статус, количество
  `matches` и `inliers`, `supported_sides`, ошибку геометрии, 4 угла и
  до 80 пар совпавших точек. Без анализа — `not_processed`.
- `GET /api/screen-search/runs/{run_id}/photos/{index}/screens/{screen_id}/crop`:
  фрагмент PNG только для сохранённого подтверждённого экрана.

Все маршруты под существующими session/Origin middleware. Запуск инференса
в HTTP **отсутствует**: тестовый запуск через CLI существующего Worker-контейнера.
Не создаётся ни второй очередь, ни новый ZIP, ни фиктивный статус обработки.
