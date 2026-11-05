# API — актуальная поверхность

База `/api`. Все маршруты кроме `GET /api/health` и `POST /api/auth/login` требуют существующую cookie session; mutating endpoints защищены Origin/Sec-Fetch-Site. JSON timestamps — UTC/ISO, photo paths наружу не выдаются новыми batch list endpoints.

## Сохранившиеся endpoints

| HTTP | Путь | Контракт |
|---|---|---|
| GET | `/health` | версия/status |
| POST/POST/GET | `/auth/login`, `/auth/logout`, `/auth/me` | sessions (не менялись) |
| POST | `/uploads` | init kind/filename/size/batch_id/sam/checksum |
| GET/PATCH | `/uploads/{upload_id}` | offsets и докачка |
| PUT | `/uploads/direct/{upload_id}` | быстрый single request, fallback PATCH |
| POST | `/uploads/{upload_id}/finish` | final SHA/Pillow validation |
| GET | `/references`, `/references/files` | список SAM/референсов |
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
| GET | `/batches/{id}` | `batch_id,photos,size_bytes,pending,runs,display_name,*_state,*_at` |
| PATCH | `/batches/{id}` | `{display_name}`, 1–120 символов |
| GET | `/batches/{id}/photos` | пагинация метаданных ФО |
| DELETE | `/batches/{id}/photos/{photo_id}` | только пока нет run |
| DELETE | `/batches/{id}` | 202 `{batch_id,state: deleting/deleted}`; **всё принадлежащее партии** |
| GET | `/batches/{id}/deletion` | `delete_state`, task progress/error |
| POST | `/batches/{id}/downloads/confirm` | `{run_id}`, лишь опубликованный полный результат |
| POST | `/batches/{id}/retention/extend` | новая дата, +2 календарных месяца |
| GET | `/batches/{id}/retention` | даты и предупреждение за 7 дней |
| GET | `/storage/usage` | mount total/used/available, inode-counted categories |

Ошибки: `401` сессия, `403` Origin, `404` не найден, `409` несовместимое состояние (после run нельзя удалить одну ФО, deleting запрещает upload/run/ZIP), `422` invalid field/threshold. `DELETE batch` фактически выполняет maintenance worker, не блокирует HTTP. Веб-UI будет использовать новые endpoints в этапе 3, до него старые вкладки остаются.

См. [MIGRATION_NOTES](MIGRATION_NOTES.md) и [DATA_LIFECYCLE](DATA_LIFECYCLE.md).

## Этап 2 — новые пути и результаты

| HTTP | Путь | Контракт |
|---|---|---|
| DELETE | `/uploads/{upload_id}` | только unfinished .part, finalized→409 |
| GET | `/batches/{id}/gallery?limit=&cursor=` | keyset 1–200, photos/next_cursor, thumbnails и original URLs |
| GET | `/references/{sam}/photos?limit=&cursor=` | keyset SAM gallery |
| GET | `/results/{run_id}/photos?sam=&group=&limit=&cursor=` | постраничные photos с реальными score/group/index |
| GET | `/results/{run_id}/sam` | counts по SAM, в т.ч. Неопределено |
| GET | `/results/{run_id}/groups` | counts по group_id |
| GET | `/thumbnails/{photo_id}` | 200 image/webp, 202 pending, 404 отсутствует |
| GET | `/thumbnails/status/{batch_id}/counts` | фактические total/ready/failed |
| POST | `/thumbnails/{photo_id}/retry` | failed/queued → queued (202) |
| GET | `/photos/{photo_id}/original` | оригинал только по DB UUID, с batch read lease |
| GET | `/runs?limit=&offset=` | runs+total, per queued `queue_position` |
| POST | `/runs` | FIFO 202, максимум 20 queued; 429 full, 409 duplicate active batch |
| GET | `/logs/{run_id}/page?limit=&cursor=` | 1–500, next_cursor; 422 устаревший segment |
| GET | `/logs/{run_id}` | ограниченный совместимый хвост (default 250) |
| GET | `/logs/usage` | bytes/budget |
| GET | `/system/status` | uptime, queue, thumbnail counts, free/reserve, recent p95 API |
| GET | `/storage/usage` | inode-dedup категории + отдельно approx pg_database_size |

**API backwards compatibility:** `GET /results/{run_id}/megaloc` до сих пор возвращает прежний manifest, `GET /download/{run_id}?sam=` стримит ZIP без постоянного файла; POST auth/cookies/Origin остаются. Browser не передаёт filesystem paths. Старые completed runs без `manifest.rows.jsonl` поддерживаются legacy fallback, но могут требовать чтения полного manifest.

**Состояния:** after upload original ready сразу, thumbnail queued/running/ready/failed независимо; `queue_position` появляется только у queued job. После crash running→interrupted; никаких ложных восстановлений промежуточных нейронных embedding. ENOSPC → HTTP 507 для новых загрузок, не удаляет completed файлы.

## Stage 3 — Vue адаптеры, новые узкие endpoints

| Метод | URI | Назначение |
|---|---|---|
| GET | `/api/references/cache/status` | total/cached по текущей подписи модели, если доступна |
| PATCH | `/api/references/sam/{sam}` | `{"new_sam":"SAM-XXXX"}`, rename SAM после подтверждения UI |
| DELETE | `/api/references/sam/{sam}` | удалить всю SAM и принадлежащие эталонные фото |
| GET | `/api/logs/{run_id}/page?tail_mode=true` | последние ограниченные события плюс курсор от конца |
| POST | `/api/system/cache/cleanup` | только cache WebP без checksum owner и устаревшие временные файлы |
| GET | `/v3/`, `/v3/fo/:id` и другие SPA пути | Vue bundle с истории маршрутов, только read-only HTML |
| GET | `/v3/assets/*` | только уже собранные Vite assets внутри `frontend/dist/assets`, без path traversal |

**Сохранённые пути:** `/` (старый интерфейс), `/static/app.js`, `/static/style.css`, login/logout, streaming ZIP, batch CRUD, queues и Base API этапов 1–2. Новые методы защищены теми же cookie/Origin middleware. При несуществующем Vue dist `/v3/` возвращает 503 и не ломает legacy `/`.

**SAM rename safety:** запрещён при queued/running/stopping MegaLoc и незавершённых загрузках данной SAM. Исторические manifests с исходными путями требуют отдельной проверки/миграции при переименовании библиотеки, прежде чем включать эту функцию на рабочем VPS. Это не изменяет MegaLoc math.

**Предупреждение о ZIP:** `GET /api/download/{run_id}` только начинает поток; отдельный пользовательский `POST /api/batches/{id}/downloads/confirm` требуется после проверки файла. UI не пытается автоматически подтвердить получение архива.

## Stage 4 — дополнительные поля и защита

- `GET /api/system/status`: добавлено поле `services.{megaloc,thumbnail,cleanup}.{alive,last_seen}` на реальном PostgreSQL heartbeat. Это совместимое **добавление**, старые поля сохраняются. Состояние `alive` означает недавно полученный сигнал процесса, не гарантирует быстроту/успешность инференса.
- `POST /api/auth/login`: после повторных неудач может вернуть HTTP 429 (bounded ephemeral throttle) вместо 401; формат cookies и DB-сессий не менялся.
- Upload finalize: изображение свыше 30 млн пикселей HTTP 422, лимит файла 60MB остаётся.
- `GET /api/download/{run_id}`: прежде чем публиковать member архив, проверяет SAM/filename на `../`, слеши, NUL и другие path escapes; формат ZIP и права / leases прежние.
- `PATCH /api/references/sam/{sam}` / `DELETE`: если SAM встретилась в опубликованном историческом manifest, возвращает HTTP 409. Записанные manifests и source References не меняются при отказе.
- Изменение БД: `0007_service_heartbeat.sql` (таблица worker presence), никакие таблицы партий, uploads, MegaLoc scores не переопределены.
