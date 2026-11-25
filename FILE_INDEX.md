# FILE_INDEX — Storage V2

Current source index for `feature/storage-architecture-v2`. Entries are actual source paths; grouped by responsibility, not a claim that every optional tool runs continuously. Historical migrations and test names remain because they preserve schema history and regressions. [Project map](PROJECT_MAP.md) explains flows; [final report](docs/STORAGE_V2_FINAL_REPORT.md) is the readiness gate.

## Deployment and contract

| Path | Purpose |
|---|---|
| `install.sh`, `.env.example` | Interactive clean install / deploy / read-only check |
| `compose.yaml`, `PhotoSorter/docker/` | Six services, protected bind mounts, one CPU app image and Caddy |
| `docs/storage-layout-v2.json` | Authoritative layout, categories, bootstrap and retention constants |
| `README.md`, `AGENTS.md`, `PROJECT_MAP.md` | Installation, rules, map |
| `.gitignore`, `.dockerignore` | Data/secrets excluded |
| `.github/workflows/ci.yml` | Backend, frontend, browser, restore, Docker Runtime |
| `.github/workflows/release-acceptance.yml` | Actual fresh Ubuntu/systemd, large real-model workload |
| `docs/STORAGE_V2_FINAL_CATALOG.md`, `STORAGE_V2_PROGRESS.md`, `STORAGE_V2_FINAL_REPORT.md` | Category catalogue, evidence and acceptance status |

## Backend and host module index

### Backend entrypoints

`PhotoSorter/backend/server/` — FastAPI, auth, DB, upload, job and worker entrypoints.

`auth.py`, `database.py`, `jobs.py`, `main.py`, `reference_cache.py`, `uploads.py`, `worker.py`.

### HTTP routes

`PhotoSorter/backend/server/api/routes/` — HTTP contracts.

`access_requests.py`, `admin_users.py`, `auth.py`, `batches.py`, `downloads.py`, `images.py`, `library_notices.py`, `logs.py`, `models.py`, `originals.py`, `processing_settings.py`, `reference_imports.py`, `references.py`, `regions.py`, `results.py`, `site.py`, `storage.py`, `system.py`, `thumbnails.py`, `updater.py`, `work_queue.py`.

### Domain services

`PhotoSorter/backend/server/services/` — Business/lifecycle operations.

`access_requests.py`, `admin_users.py`, `archive_cache.py`, `archive_layout.py`, `archive_pipeline.py`, `archives.py`, `auto_processing.py`, `batch_runs.py`, `batches.py`, `cleanup.py`, `compute_settings.py`, `construction_catalog.py`, `construction_relabel.py`, `disk_guard.py`, `heartbeat.py`, `library_notices.py`, `media_preparation.py`, `operations.py`, `reference_archives.py`, `reference_gallery.py`, `reference_gc.py`, `reference_imports.py`, `reference_publication.py`, `reference_sides.py`, `reference_uploads.py`, `references.py`, `regions.py`, `result_pages.py`, `retention.py`, `storage_admin.py`, `storage_breakdown.py`, `storage_inventory.py`, `storage_maintenance.py`, `storage_usage.py`, `temp_cleanup.py`, `thumbnail_gc.py`, `thumbnails.py`, `update_gate.py`, `upload_manifest.py`, `upload_validation.py`, `worker_cpu_affinity.py`.

### File ownership and registry

`PhotoSorter/backend/server/storage/` — Typed paths, ownership, inode accounting, reservations, cleanup.

`accounting.py`, `admission.py`, `batch_cleanup.py`, `bounded.py`, `hardlinks.py`, `ownership.py`, `paths.py`, `reconciliation.py`, `reference_lifecycle.py`, `reference_objects.py`, `registry.py`, `reporting.py`, `reservations.py`, `result_audit.py`, `thumbnail_cache.py`.

### DB repositories

`PhotoSorter/backend/server/db/repositories/` — Transaction SQL.

`access_requests.py`, `batches.py`, `job_status.py`, `pagination.py`, `reference_imports.py`, `reference_versions.py`, `work_queue.py`.

### Worker roles

`PhotoSorter/backend/server/workers/` — Background processes.

`cleanup.py`, `media_prepare.py`, `reference_prepare.py`, `thumbnail.py`, `warm_megaloc.py`.

### Media

`PhotoSorter/backend/server/media/` — Inspection, normalization, preview and video.

`estimate.py`, `formats.py`, `preview.py`, `sorting.py`, `video.py`.

### Security

`PhotoSorter/backend/server/security/` — Access policy.

`access_policy.py`, `login_throttle.py`.

### Storage policy and safe FS

`PhotoSorter/backend/app/storage/` — Contract, config, path/key validation, native scratch.

`categories.py`, `changes.py`, `config.py`, `entrypoint.py`, `filesystem.py`, `paths.py`, `temporary.py`.

### Run lifecycle

`PhotoSorter/backend/app/jobs/` — Runtime and progress.

`overall_progress.py`, `progress.py`, `runtime.py`, `worker.py`.

### Recognition

`PhotoSorter/backend/app/recognition/` — Frozen MegaLoc math.

`engines/base.py`, `engines/megaloc/extractor.py`, `engines/megaloc/loader.py`, `errors.py`, `grouping/finder.py`, `matching/resolver.py`, `math.py`, `pipeline.py`.

### Result export

`PhotoSorter/backend/app/results/` — Immutable media and metadata.

`copier.py`, `exporter.py`, `match_filter.py`, `repository.py`, `sides.py`.

### Model assets

`PhotoSorter/backend/app/system/` — Model bundle, download, offline cache.

`downloads.py`, `model_store.py`, `performance.py`, `technical_cache.py`.

### App logging

`PhotoSorter/backend/app/logging/` — Bounded journals.

`events.py`, `service.py`.

### Photo utilities

`PhotoSorter/backend/app/photos/` — Input, construction labels.

`construction.py`, `labels.py`, `reader.py`, `scanner.py`.

### Host maintenance

`PhotoSorter/tools/maintenance/` — Install, updater, host metrics, CI, snapshot and restore.

`audit_containerd.py`, `audit_host.py`, `audit_live.py`, `audit_write_sites.py`, `bootstrap_storage.py`, `ci_fresh_ubuntu.sh`, `ci_infra_update.py`, `ci_megaloc_offline.py`, `ci_release_load.py`, `ci_restore_drill.py`, `ci_vm_health.py`, `compare_baseline.py`, `host_accounting.py`, `host_logs.py`, `install_map_updater.sh`, `install_prerequisites.sh`, `map_build.py`, `map_updater.py`, `setup_tcp_bbr.sh`, `smoke_container.sh`, `snapshot.py`, `staging_probe.py`, `test_install_prerequisites.sh`.

### Web API

`PhotoSorter/frontend/src/api/` — Typed HTTP clients.

`accessRequests.ts`, `adminUsers.ts`, `batches.ts`, `client.ts`, `libraryNotices.ts`, `logs.ts`, `referenceImports.ts`, `references.ts`, `regions.ts`, `results.ts`, `runs.ts`, `system.ts`, `workQueue.ts`.

### Web app

`PhotoSorter/frontend/src/app/` — Router and app shell.

`App.vue`, `router.ts`.

## Frontend

`PhotoSorter/frontend/src/features/` contains `admin/`, `auth/`, `fo/`, `logs/`, `queue/`, `references/`, `results/`, `settings/`. Shared UI belongs to `components/`; `composables/`, `stores/`, `utils/`, `types/` and `styles/` keep cross-feature behavior out of page components. Production uses only compiled Vite dist served by FastAPI; no Node runtime.

## PostgreSQL and tests

45 versioned SQL migrations: `0001_batch_lifecycle.sql` through `0046_storage_admission.sql`. Migrations 0037–0046 implement V2 ownership, storage, registry and quota changes; 0040 removes obsolete archive retries. Never delete migration history or rewrite applied migrations. `server/db/migration_runner.py` applies them in order.

66 backend test modules in `PhotoSorter/backend/tests/`; historical stage names are regression coverage, not alternate production versions. Frontend Vitest and Playwright check current UI. `ci_fresh_ubuntu.sh`, `ci_vm_health.py`, `ci_release_load.py` are disposable CI-only acceptance harnesses, never installation commands on production.

## Operations

[Deployment](docs/DEPLOYMENT.md), [backup/restore](docs/BACKUP_RESTORE.md), [rollback](docs/ROLLBACK.md), [operations](docs/OPERATIONS.md), [data lifecycle](docs/DATA_LIFECYCLE.md), [reference pipeline](docs/REFERENCE_PIPELINE.md), [contract](docs/STORAGE_ARCHITECTURE_V2.md).

- `PhotoSorter/tools/maintenance/storage_tree.py`: independent bounded physical tree census and comparison, including directories.
- `PhotoSorter/backend/server/storage/upload_part_lock.py`: per-part kernel lease around FO append and receipt, nonblocking diagnostic probe.

- `PhotoSorter/tools/maintenance/disk_tree.py`: independent root-device physical census and lower-bound deleted-open FD observations.
- `PhotoSorter/tools/maintenance/storage_check_history.py`: bounded host measurement history.
- `PhotoSorter/frontend/src/features/admin/storage/StorageControl.vue`: byte-level control, residuals, unknown objects and history; no request-time disk scan.
