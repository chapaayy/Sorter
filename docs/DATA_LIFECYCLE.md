# Storage V2 — жизненный цикл и безопасность данных

Активные пути определены [машинным контрактом](storage-layout-v2.json), все категории — [каталог](STORAGE_V2_FINAL_CATALOG.md). Не применять команды прежних data/Models.

| Данные | Физический владелец | Когда освобождаются |
|---|---|---|
| Original FO, normalized, result media/metadata | `app/users/{user_id}/batches/{batch_uuid}/` | Явное удаление или наступившая retention, после остановки работ и IO leases; immutable files |
| Personal WebP | `app/users/{user_id}/thumbnails/` | Только после исчезновения всех owner-scoped dependencies и 24h grace |
| Shared CAS, reference WebP/NPY | `app/shared/references/` | После current/history/job/import dependencies и grace, повторная проверка под locks |
| FO/reference parts | `app/temporary/uploads/` | Finalize/cancel или 30d idle, только без активных transfer leases |
| Native scratch, transcode, frames, export staging | `app/temporary/` | finally/terminal или proven abandoned, grace/typed lease |
| ZIPs | `app/temporary/archives/` | 3600 s от публикации + sweep, active reader/build pin prevents deletion |
| Verified model | `app/models/megaloc/` | Только explicit verified replacement/repair |
| Provider cache | `app/cache/` | Только подтверждённое offline host maintenance |
| PGDATA, Caddy TLS, root updater, logs | infrastructure/system/logs | Отдельные native/host policies; никогда batch cleanup |

## Upload and processing

Batch `upload_state`: open / ready / sealed. Manifest `waiting/complete` подтверждается точными upload UUID, lengths and finalize receipts, not UI counts. Resume получает фактический offset; accepted part reservation уменьшается по подтверждённым байтам. Original публикуется без изменения; normalized JPG/MP4 принадлежит тому же owner. Один FIFO обрабатывает normalization/reference preparation/FO. Job progress, state and immutable version pin authoritative in PostgreSQL. Output media and JSONL metadata are published together by atomic rename; partial staging is not a valid result. Old results remain until business deletion.

## Delete and retention

`delete_state: active → deleting → deleted`, ошибка `delete_failed`, повторный DELETE возобновляет idempotent cleanup. Trusted IDs from PostgreSQL, no client-supplied path. Wait for stop jobs and active read/write leases; delete only typed owner/run/temporary paths; preserve other owners, model, shared reference dependencies, native databases and TLS. Cleanup tasks and tombstones reflect actual progress. Normal retention for new completed FO is enabled, two calendar months default; operator may configure or disable. Changes do not arbitrarily reset existing deadlines; re-enabling gives expired batches a new configured period. ZIP download is not a condition of retention. Explicit delete independent. No quota-triggered automatic eviction.

## Shared references

One physical object per content SHA, independent construction/member IDs. Claim pins version and model. Unpinned superseded version members may retire after 30 days; all current and retained job pins protect the graph. After last dependency 24h grace, recheck with exclusive lock. No TTL for active embeddings, model or active shared objects. Gallery is virtual PostgreSQL projection. Personal previews shared only within same owner. Historical version headers retained, no arbitrary old-version restoration UI.

## Hardlinks and accounting

Only safe exclusive link on same filesystem and immutable source; copy fallback when required. Removing one link does not free blocks while other names or open descriptors exist. Logical/allocated/personal/reserved distinct. Registry and reconciliation report orphan/unknown/missing evidence, not delete arbitrary files. Temporary ZIP and shared protected objects never personal charge. Limits disabled by default; physical guard always active. See [architecture](STORAGE_ARCHITECTURE_V2.md).

## Download presentation

Archive assembled solely by authorized GET on demand; existing valid ZIP reused, CRC and Range supported, response lease ends on completion/error/abort. Date is manual or processing date from batch/run metadata; construction and side folders are presentation. Do not use archive member names as filesystem authority. Video appears in its own branch, temporary recognition frames never included.

[Operational guide](OPERATIONS.md) · [Backup and restore](BACKUP_RESTORE.md) · [Final acceptance](STORAGE_V2_FINAL_REPORT.md).
