# MAP — актуальная карта проекта Storage V2

Ветка `feature/storage-architecture-v2`. Только чистая установка; статус готовности — [финальный отчёт](docs/STORAGE_V2_FINAL_REPORT.md). История прежней архитектуры остаётся в Git, не используется как инструкция.

```text
Browser: Vue 3 / TypeScript / Pinia / Vue Router
  /fo, /fo/:batchId       uploads, resume, gallery, processing
  /references            shared library / regions / sides
  /queue                 unified FIFO and history
  /results, /results/:id immutable results and ZIP
  /admin                 owner: users, models, performance, storage, updater
  /settings, /logs, /login, /register
     │ HTTPS same origin
     ▼
Caddy :80/:443 ───► FastAPI api:8000 ───► PostgreSQL 17
                       │ auth, services, storage registry │
                       ├─ managed /storage/app (common mount)
                       └─ restricted Unix RPC ─► map-updater.service (host)
PostgreSQL work_queue ──► worker (FIFO leader)
                          ├─ media normalization
                          ├─ reference preparation and publication
                          └─ real CPU MegaLoc / grouping / matching / result export
PostgreSQL thumbnail_tasks ──► thumbnail worker ─► scoped WebP cache
PostgreSQL cleanup tasks ──► cleanup worker
                            ├─ batch / run deletion, retention
                            ├─ temporary and reference GC
                            └─ bounded registry reconciliation
Host systemd timer ──► bounded PostgreSQL log maintenance
Host updater ──► protected backups / isolated BuildKit / approved branch
```

## Responsibilities

| Area | Source root | Responsibility |
|---|---|---|
| Web UI | `PhotoSorter/frontend/src/` | One SPA; typed APIs, reusable components, feature screens |
| HTTP | `PhotoSorter/backend/server/api/routes/` | Authenticated contracts, downloads, result pages, owner-only actions |
| Domain | `server/services/`, `server/uploads.py`, `server/jobs.py` | Upload receipts, FIFO use cases, reference versions, lifecycle |
| DB | `server/db/`, `server/database.py` | Versioned schema, repository SQL, transaction coordination |
| Storage | `app/storage/`, `server/storage/` | Single typed path contract, file safety, physical registry, reservations and ownership |
| Inference | `app/recognition/`, `app/jobs/`, `app/results/` | Frozen MegaLoc math, job execution, immutable output |
| Model | `app/system/`, `server/reference_cache.py` | Verified offline model bundle, separate persistent reference features |
| Infrastructure | `install.sh`, `compose.yaml`, `PhotoSorter/docker/` | Clean install, one app image, isolated protected mounts |
| Host tools | `PhotoSorter/tools/maintenance/` | Root updater, maintenance, diagnostics, staging backup/restore and acceptance |
| CI | `.github/workflows/ci.yml`, `release-acceptance.yml` | Ordinary regression plus real VM and workload gates |

Paths in backend rows are relative to `PhotoSorter/backend/`. See [file index](FILE_INDEX.md).

## Managed data tree

```text
storage/
  app/
    users/{user_id}/
      batches/{batch_uuid}/{originals,normalized,results/{run_id}/{media,metadata}}/
      thumbnails/v{version}/{prefix}/
    shared/references/{objects,embeddings,thumbnails}/
    temporary/{uploads,transcoding,video-frames,processing,archives,scratch,model-downloads}/
    models/megaloc/{weights,source,metadata}/
    cache/{huggingface,torch,xdg}/
    state/runs/                reserved, no active run JSON writer
  infrastructure/
    postgres/data/
    caddy/{data,config}/
  logs/{api,worker,thumbnail,cleanup,processing,models,postgres,caddy,updater,audit}/
  system/{audits,backups/updater,updater,state}/
```

The gallery is a DB projection; no second physical reference gallery. FO embedding vectors are currently in RAM. See the [machine contract](docs/storage-layout-v2.json) and [51-category catalogue](docs/STORAGE_V2_FINAL_CATALOG.md), including external engine/OS/configuration boundaries.

## Data flow and invariants

**FO:** owner registers batch and exact UUID manifest; the upload receipt reserves space. PATCH writes managed part files, validates offset, content, size and checksum. Finalization publishes immutable original; normalized media is a persistent derivative, not temporary. FIFO sorts once; hardlinks/copies and JSONL metadata are published atomically. SQL owns job state and versions. Results never require a prebuilt ZIP.

**References:** preview compares SHA-256 within construction. One import session, typed part paths, shared content-addressed objects, immutable library version publication. At FIFO claim, FO pins the current version and model signature. Shared object and embedding dependency checks protect all retained versions/jobs. Addresses and side labels are metadata. Separate export/import of portable side metadata from main is not part of this release.

**ZIP:** authorized HTTP request builds and validates a temporary ZIP for full run, construction or references. Range uses the same immutable published file, guarded by leases. TTL 3600 seconds from publication, not last access; cleanup never touches active readers or protected objects. Report date and side belong to archive presentation, not filesystem ownership keys.

**Storage:** one PostgreSQL registry tracks path, owner, logical length, allocated blocks, inode identity and charge. Durable receipts and transient leases reserve future bytes. Reconciliation observes and reports unknown/missing/orphaned data; it is not a deletion engine. Root host sample accounts separately for protected infrastructure and logs; Docker/OS shared bytes are not claimed as MAP physical bytes.

**Permissions:** owner manages all current working data; viewer accesses only explicitly granted published runs. No browser-controlled filesystem paths, Docker socket, PGDATA or TLS keys mounted into the application. Updater checks the pinned feature branch and runs only fixed commands through Unix RPC.

## Health and deployment

PostgreSQL and API have Docker-native healthchecks. Caddy needs an actual HTTPS request; worker, thumbnail and cleanup need fresh DB heartbeats. `docker compose ps` alone does not prove functional health. Systemd starts Docker, updater and log timer; Docker restart policies recover containers. VM acceptance verifies changed boot ID, per-service health, new advancing heartbeat instances and data hashes after reboot and update.

See [installation](docs/DEPLOYMENT.md), [lifecycle](docs/DATA_LIFECYCLE.md), [backup/restore](docs/BACKUP_RESTORE.md), [operations](docs/OPERATIONS.md), [architecture](docs/STORAGE_ARCHITECTURE_V2.md) and [progress](docs/STORAGE_V2_PROGRESS.md).

- Independent host storage-tree check: `host_logs.py → storage_tree.py → storage-host.json → /api/storage/usage`; physical directory blocks and signed comparison separate from quota ledger. FO chunk append and receipt use a per-part kernel lease, observed nonblocking by registry.

- Root-device physical census: `disk_tree.py` reuses the bounded tree walker, excludes mountpoints, measures visible Docker/default containerd/system paths, and samples unlinked FDs. `storage_check_history.py` preserves bounded measurement history in the existing host report; Vue `StorageControl.vue` renders observations and incomplete states.
