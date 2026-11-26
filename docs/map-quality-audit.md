# MAP — инженерный аудит качества, открытый этап

Baseline: `407b786383f6ee166822fe08a76a20164eb3747a`, branch `feature/storage-architecture-v2`.
This is an interim audit, not production acceptance. No main changes, merge, force push, or working VPS operations.

## Accepted evidence from the preceding stage

- [CI 45891910652](https://github.com/chapaayy/Sorter/actions/runs/45891910652): success; backend, frontend, restore, docker-runtime, Chromium desktop, WebKit desktop and mobile (7/7).
- [Release 45891910444](https://github.com/chapaayy/Sorter/actions/runs/45891910444): success; scope, clean Ubuntu/systemd, browser preflight, realistic load (4/4). Status observed through GitHub Actions jobs, not a fresh local execution.
- Baseline diff from f776f6b: four commits, 25 files. Previous three bug fixes are accepted on this revision, not a proof of every new scenario.
- Source tree obtained without truncation; existing architecture, migration 0053, CI and release workflows, reference/ownership/storage sources and related existing documentation reviewed selectively. Old account-role progress/testing documents are not authoritative for the current role implementation.

## Findings

### MAP-QA-001 — P1: account deletion can leave its tasks active until global lease is granted
Evidence: baseline `PhotoSorter/backend/server/services/account_lifecycle.py`, request (around 48–91), _delete/run_pending (around 248–305); cleanup.request (around 18–54); account_activity.lease.
Reproduction specification: seed two personal jobs (running and queued), another account's queued job, retain a shared account activity lease. Submit a delete request. Baseline revokes sessions but does not mark batches deleting or request worker cancellation until the exclusive lease becomes available. Other API activity can delay this; a queued task can be claimed in the interim.
Expected: a successful delete request must durably cancel queued jobs and signal running jobs in the same transaction; no IO deletion before worker/IO leases release; other accounts unaffected.
Change: c36a1342f81a7c2c77ff813e51264fadd59d2dc8. Reuse cleanup.request_locked with FIFO lock, cancel waiting auto processing, leave existing cleanup/registry recovery mechanisms and final account deletion gate intact. Shared library is not deleted; transfer behavior unchanged. New API/PG/filesystem test test_delete_account_cancels_fifo_before_exclusive_lease_and_preserves_other_owner; synthetic job states and lease, not actual MegaLoc/FFmpeg or a real ZIP stream.
Status: source-confirmed ordering defect, fixed in code; new test not yet verified by the auditor. Full deletion acceptance remains open: live uploads, FFmpeg, ZIP stream/build, cancellation after last write, concurrent activity, stale reservation recovery, unknown personal paths, repeated process termination/restart and explicit deletion stage/progress in admin UI.

### MAP-QA-002 — P2: independently sampled host bytes can produce a false discrepancy
Evidence: baseline storage_tree.py compare at line 113 onward and host_logs.py _publish_usage around 193–197. The host census had only one sample before independent traversal; app registry had before/after evidence. Observed read-only production report: app delta 0, host delta +4096, no unknown/missing/error objects; a later independent report had both deltas 0. This demonstrates a transient observation, not the identity of the file that changed.
Reproduction specification: append a physical block to a host file between the host sample and independent walk. Baseline reports a comparable nonzero discrepancy even if the app registry is stable.
Change: c36a1342f81a7c2c77ff813e51264fadd59d2dc8, bracket independent scan with fresh host samples and order-independent path/inode/block/type fingerprint; vanished host nodes make the sample partial. Do not publish a confirmed mismatch if host evidence changed. True stable mismatch must still be counted exactly, without tolerance. Preserve previous comparable result when new sample incomplete. No change to storage/TTL/quota policy.
Regression: test_infrastructure_growth_during_independent_walk_is_not_comparable on temporary filesystem, including stable zero and deliberately stable 4096-byte undercount; existing hardlink/GNU du tests retained. Status: code-level defect fixed; test execution pending. Live census remains non-atomic; equal bracketing evidence cannot exclude every possible transient change.

### MAP-QA-003 — P0: import permission alone exposes/mutates other actors' staging sessions
Evidence: baseline routes/reference_imports.py 84–138; services/reference_imports.py create (114–118), register_manifest (146–166), status/list_sessions (235 onward); db/repositories/reference_imports.py create_session uses ON CONFLICT DO NOTHING; security/route_permissions.py maps routes to references.import without object scope. Migration 0053 already records requested_by.
Reproduction specification: two authenticated accounts with references.import; A creates a staging session with private filename and manifest. B uses A's UUID in GET, repeated POST, manifest, file chunk/finish/duplicate/complete; old handlers do not check actor. List also returns all sessions. Shared published reference rights do not imply right to interfere with another actor's pending upload.
Change: 1da312a93b5f287455bd31e7c13341ff17c12bf7. Scope staging sessions to requested_by for non-owner; check collision after insert in same transaction; protect nested file operations and scope list before pagination. Owner retains administrative/legacy-session recovery; NULL historical requester is not assigned to a new employee. Existing shared library/global queue rights remain unchanged. No migration.
Regression: test_reference_import_sessions_are_not_shared_by_client_uuid uses three real API accounts and real PostgreSQL with staged manifest. Verify list, duplicate client UUID, nested read/write and no changes to original offset. Status: source-confirmed authorization defect; fix and regression committed, runtime acceptance pending. No actual attack on production performed.

## Open risks (not runtime-confirmed)

- MAP-QA-R01: personal_activity.py:75 uses DISTINCT ON(kind,bucket); faviconState.ts:23,41 retains a single error. Multiple outcomes between polls may be lost and acknowledgement can hide an earlier failure. Need define bounded multi-outcome API/ack semantics and test real two-error sequences including ZIP/cleanup. No UI redesign in this increment.
- MAP-QA-R02: images.py:71 returns unleased FileResponse for non-video, non-reference images, unlike ZIP and video. Batch cleanup does not consult the global API lease for ordinary batch deletion. Test race between authorized image read/Range and batch cleanup; use existing batch lease if reproduced. Do not weaken filesystem/path checks.
- MAP-QA-R03: account deletion finalization still depends on _busy, reconciliation, and exclusive global lease; active unrelated transfers may delay final publication. Unknown files deliberately fail closed. Need targeted fault injection and per-owner cleanup verification before declaring full lifecycle complete.
- MAP-QA-R04: result catalog still uses offset under concurrent insertion/deletion; possible repeated/omitted cards between pages. Verify using real DB plus concurrent browser refresh and permission revocation.
- MAP-QA-R05: permission changes during streaming, stale browser responses, same-tab switching, direct HEAD/Range, delegated role changes under concurrent requests, old NULL requester recovery require dedicated coverage.
- MAP-QA-R06: host fingerprint/registry brackets are not a filesystem snapshot; retry behavior under sustained writes and overhead on representative isolated storage must be measured. Do not silently treat incomplete checks as zero.

## Coverage matrix

Legend: baseline pass = prior actual CI for unchanged revision; reviewed = source inspection only; added = new regression in repository, not yet executed/accepted by auditor.

| Area | Evidence / current state | Required outstanding checks |
|---|---|---|
| Accounts / access | baseline pass; account_acceptance, account_roles, permission_scopes; reviewed access_policy, route_permissions, accounts, admin_users, access_requests, reference_imports; added actor isolation and delete tests | full role matrix + direct object routes, concurrency and revocation; CSRF, session switches; real three-account simultaneous workflow |
| FIFO / workers | baseline pass; work_queue, jobs/cleanup paths reviewed selectively; added delete cancellation regression | claims/stop/restart/blocking/auto-queue race; live MegaLoc/FFmpeg |
| Upload / media | baseline acceptance, selected reference_uploads/uploads and reservation contracts reviewed | parallel resumable chunks, corrupt media, quotas/disk full, cancellation and session switch, browsers |
| References / results | baseline pass; staging, result catalog/detail reviewed selectively; added staging authorization regression | concurrent library pin/publication, sides/regions, actual result fixtures, cursor/pagination |
| ZIP / deletion | baseline load and restore success; operations, file_response, downloads, batch_cleanup reviewed; added synthetic-state deletion regression | actual ZIP stream/build and disconnect with delete; all private paths/reservations after crash; account status/progress |
| Storage V2 | baseline pass; observed 4096 transient host residual; added independent bracketing regression | run new host tests, measure live retry overhead, verify actual physical accounting before/after full deletion, disk-full and stale leases |
| Favicon | source inspection (personal_activity, useFaviconStatus, faviconState); baseline existing tests | multi-error loss, exact acknowledgement, stale API, browser/renderer and cross-tab scenarios |
| UI | baseline browser matrix green, new account confirmation wording | full role-specific screen walkthrough, dialog interactions, live browser API and accessibility |
| Install/update/restore | baseline CI restore, Docker and clean Ubuntu/systemd successful | reaccept affected updater/host contracts and review rollback on new HEAD |
| Cross-system | baseline realistic-load success | simultaneous three-account real uploads, reference preparation, actual inference, native ZIP, deletion/restart; not yet executed for audit |

## Execution and limits

Local git clone failed (DNS for github.com); container has pytest but no Docker or PostgreSQL executable. GitHub connector read and committed tracked text, checked diffs and pushed fast-forward only with expected SHA. New test suite execution delegated to existing automatic workflows; no workflow edits or manual duplicate triggers. At checkpoint c36a134 CI 45894317052 / acceptance 45894316993 and 1da312a CI 45894428937 / acceptance 45894429021 were in progress. Corrected new fixture to use file status offset, not manifest received, and made host stability compare allocated bytes rather than logical sizes. These are not claimed passing until actual jobs finish. No schema migration, new storage category, TTL change, or production deployment. Full audit remains OPEN.
