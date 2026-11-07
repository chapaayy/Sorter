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

Из `/processing` удалена UI-форма нового запуска. `POST /runs` и повторная сортировка по-прежнему поддерживаются backend, кнопки запуска находятся в `/fo`. Все результаты и история остаются доступны. Реальные сетевые/ВПС сценарии — `docs/STAGE4_ACCEPTANCE.md`.

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
| GET | `/`, `/fo/:id`, `/references`, `/processing`, `/results`, `/logs`, `/settings` и другие SPA пути | Единственный Vue bundle, history fallback, только read-only HTML |
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

## Stage 4: единая очередь и уведомления

`GET /api/work-queue?scope=active|history|all&limit=100&offset=0` отдаёт задачи двух видов в порядке `seq` (для active — ASC, history — DESC), реальные статусы подготовки, счётчики и batch display_name. `GET /api/reference-imports` возвращает сессии и количество переданных/дублирующихся файлов при включённом staged режиме. `GET /api/reference-library/status` возвращает опубликованную версию и флаги `unified_queue_enabled`, `staged_imports_enabled`, а также `notice`, `notice_version_id`, `pending_changes`, `message`. `GET /api/reference-library/events` отдаёт историю изменений с actor/details. `POST /api/reference-library/notices/ack` с `version_id` — единственная операция подтверждения (монотонный cursor). HTTP GET ни в одном случае не признаётся показом. Для подготовки: `POST /api/reference-preparations/{id}/retry|skip` с `idempotency_key`, `POST /stop` на выполняющееся задание. Актуальная инструкция: [REFERENCE_QUEUE_STAGE4](REFERENCE_QUEUE_STAGE4.md).
