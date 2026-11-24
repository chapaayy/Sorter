# Storage V2 — полный каталог

Сформировано из `storage-layout-v2.json`, 51 категорий. Пути относительны к host storage root (по умолчанию `/opt/Sorter/storage`); @ обозначает управляемую внешнюю границу, не папку приложения. Контракт является источником правил. Наличие строки не доказывает фактическую запись в каждой категории: run_state зарезервирована, reference_gallery виртуальна, fo_embedding_temp в RAM. Остальные категории проверяются профильными тестами и финальной сверкой. Неизвестные объекты не удаляются автоматически.

| Категория | Путь | Область | Производитель | Удаление | Применение |
|---|---|---|---|---|---|
| `fo_original` | `app/users/{user_id}/batches/{batch_uuid}/originals/{upload_uuid}.{ext}` | personal | upload finalize | business deletion with operation lease | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `fo_normalized` | `app/users/{user_id}/batches/{batch_uuid}/normalized/{upload_uuid}.{ext}` | personal | media prepare | source/run dependency check | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `result_media` | `app/users/{user_id}/batches/{batch_uuid}/results/{run_id}/media/` | personal | result exporter | run/file deletion with leases | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `result_metadata` | `app/users/{user_id}/batches/{batch_uuid}/results/{run_id}/metadata/` | personal | result exporter | run deletion with leases | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `run_state` | `app/state/runs/{run_id}/` | personal | jobs/runtime | run history policy | Run state authoritative in PostgreSQL; reserved directory only, no active JSON run-state writer. |
| `fo_thumbnail` | `app/users/{user_id}/thumbnails/v{version}/{prefix}/{hash}.webp` | personal | thumbnail worker | all dependencies absent + 24h grace + recheck | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `reference_object` | `app/shared/references/objects/{prefix}/{sha256}` | shared | reference import | all current/history/pins absent + grace + recheck | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `reference_gallery` | `app/shared/references/gallery/{construction_id}/` | shared | reference publication | publication/deletion under library lock | Virtual gallery from PostgreSQL; directory reserved, unexpected files diagnosed; no materialized duplicate gallery. |
| `reference_thumbnail` | `app/shared/references/thumbnails/v{version}/{prefix}/{hash}.webp` | shared | thumbnail worker | all dependencies absent + grace + recheck | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `reference_embedding` | `app/shared/references/embeddings/{model_signature}/{prefix}/{sha256}.npy` | shared | reference preparation | all version/job dependencies absent + grace + recheck; no TTL | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `fo_upload_part` | `app/temporary/uploads/fo/{batch_uuid}/{upload_uuid}.part` | temporary | upload PATCH | commit/cancel or 30d inactivity with no holder | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `reference_upload_part` | `app/temporary/uploads/references/{session_uuid}/{upload_uuid}.part` | temporary | reference transfer | commit/cancel or 30 days idle with transfer lock and recheck | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `transcode_temp` | `app/temporary/transcoding/{task_id}/` | temporary | FFmpeg | success/failure or confirmed abandoned task | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `video_frames` | `app/temporary/video-frames/{run_id}/` | temporary | video extraction | run completion/error or proven abandoned | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `processing_staging` | `app/temporary/processing/{run_id}/` | temporary | MegaLoc/export | published/terminal or confirmed abandoned | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `fo_embedding_temp` | `app/temporary/processing/{run_id}/features/` | temporary | recognition if ever spilled | after run/lease release | MegaLoc FO embeddings currently in memory; namespace reserved, no persistent writer. |
| `zip_results` | `app/temporary/archives/results/{run_id}/` | temporary | HTTP download | 3600s since publication; no active builder/reader | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `zip_construction` | `app/temporary/archives/results/{run_id}/` | temporary | HTTP construction download | 3600s since publication; no active builder/reader | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `zip_references` | `app/temporary/archives/references/{cache_key}.zip` | temporary | HTTP reference export | 3600s since publication; no active builder/reader | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `zip_fragment` | `app/temporary/archives/` | temporary | archive builder | error/finally or stale with exclusive lock | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `archive_lock` | `app/temporary/archives/` | temporary | archive cache | only no possible holder/waiter | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `atomic_fragment` | `app/temporary/scratch/{service}/{operation_id}/` | temporary | atomic helper | finally or expired unlocked scratch lease | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `model_download` | `app/temporary/model-downloads/{task_id}/` | temporary | model downloader | success/error or bounded resume | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `model_weights` | `app/models/megaloc/weights/` | protected | model installer | explicit model replacement only | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `model_source` | `app/models/megaloc/source/` | protected | model installer | explicit model replacement only | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `model_metadata` | `app/models/megaloc/metadata/` | protected | model installer | explicit replacement only | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `technical_cache` | `app/cache/{provider}/` | system | HF/Torch/XDG | only explicit offline purge of torch, huggingface and xdg provider roots after independent verified bundle; exclusive runtime guard | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `scratch` | `app/temporary/scratch/{service}/{operation_id}/` | temporary | native libraries/FFmpeg | close/finally or lease-aware GC | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `postgres_data` | `infrastructure/postgres/data/` | infrastructure | postgres | only PostgreSQL manages | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `caddy_state` | `infrastructure/caddy/{state_kind}/` | infrastructure | caddy | only Caddy manages | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `service_log` | `logs/{service}/` | system | service logging | closed segments by budget/age | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `run_log` | `logs/processing/{run_id}/` | system | processing logger | budget and run deletion; never active segment | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `access_log` | `logs/caddy/access/` | system | Caddy | native bounded rotation | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `audit_snapshot` | `system/audits/` | host_private | host audit | latest + bounded history | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `audit_event` | `logs/audit/` | system | opt-in observer | closed session expiry | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `updater_backup` | `system/backups/updater/` | host_private | updater | retain latest verified rollback; prune only own old sets | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `updater_workspace` | `system/updater/workspace/` | host_private | updater/build | finally or own abandoned operation | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `builder_marker` | `system/updater/private/` | host_private | map_build | own builder cleanup only | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `updater_control` | `system/updater/control/` | host_private | updater | no unlink of live lock; explicit recovery | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `installation_state` | `system/state/` | host_private | installer | no automatic deletion | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `runtime_image` | `@docker/images` | engine | Docker/BuildKit | own unused marked images, retain current/previous | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `build_cache` | `@docker/buildkit` | engine | disposable builder | remove own builder only | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `system_runtime` | `@host/runtime` | external | OS/engine/updater | native lifecycle; no app deletion | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `tmpfs` | `@memory/tmpfs` | external | OS/container runtime | close/restart | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `unknown` | `@unclassified` | unknown | unknown | never automatic deletion | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `deployment_config` | `@project/.env-and-generated` | external | install.sh and updater | explicit operator replacement only | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `host_config` | `@host/etc-and-systemd` | external | install_prerequisites.sh, install.sh, setup_tcp_bbr.sh | only explicit operator or installer-owned obsolete configuration | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `external_backup` | `@operator/backup` | external | snapshot.py and restore drill | operator retention, no MAP GC | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `test_artifact` | `@test/sandbox` | external | pytest, Playwright, CI Docker and restore | test/CI cleanup only | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `external_diagnostic` | `@operator/diagnostic` | external | staging_probe.py explicit output and manual diagnostics | operator retention | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |
| `client_storage` | `@browser/profile` | external | frontend localStorage, HTTP download and browser file selection | browser/user controls only | See producer, consumer, lifecycle and acceptance evidence in STORAGE_V2_PROGRESS.md. |

## Правила

- UID/GID app 10001/10001; private system и инфраструктура не монтируются в app. Корень должен быть закреплён для всей установки.
- ZIP TTL 3600 секунд, обход 30 секунд; активные ZIP и leases защищены. Не путать TTL с retention ФО.
- Незавершённые ФО: 30 дней; grace миниатюр 24 часов; история образцов 30 дней, orphan grace 24 часов; реальные зависимости проверяются прежде удаления.
- Личные квоты по умолчанию выключены. Резервирование учитывает ожидаемую запись, реестр — подтверждённые объёмы. Hardlinks физически учитываются один раз; общие образцы/модели/ZIP не включаются в личную квоту.
- Внешние Docker layers, файловая метаинформация, чужие процессы ОС и системные журналы не являются личной квотой. Отчёт хоста — наблюдение, а не разрешение удалять неизвестные файлы.
