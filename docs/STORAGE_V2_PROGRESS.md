# MAP Storage V2 progress
Branch: feature/storage-architecture-v2; base: c6d77ebb1c9c80c732df209a17a993dd38ec381f. Main read only. No deploy, migration of old data, or merge.
## Stage status
1. **ACCEPTED — 2026-11-24** — 96 remaining modules mapped, 573 original candidate lines dispositioned, 35 migrations indexed, 51 categories (45 + 6 external boundaries), consumer/native dependency review and documentation corrections committed. Coverage tests added. Do not claim fully exhaustive source/runtime tracing or acceptance until current-head checks pass.
2. Root and foundations — in progress.
3. Personal pipeline — not started.
4. References — not started.
5. Temporary pool, ZIP and models — not started.
6. Logs and infrastructure — not started.
7. Accounting and reconciliation — not started.
8. Admin — not started.
9. Disabled-by-default quotas — not started.
10. Final install and PR (no merge) — not started.
## Baseline
[Actions run 45408161752](https://github.com/chapaayy/Sorter/actions/runs/45408161752) at exact base SHA succeeded: backend, restore, frontend, chromium-desktop, webkit-desktop, webkit-mobile, docker-runtime. Prior WebKit mobile failures not reproduced by that run; this is not proof of absence of flakiness.
## Findings and blockers
Existing config and storage paths, compose, database, migrations 0001–0036 (35 files), update gate, archive compatibility service, audit write-site helper and key project docs inspected for dependency evidence. See catalog and source/schema indexes; lexical candidates are not a semantic review. AGENTS, PROJECT_MAP and active docs corrected to ZIP on demand; actual archive_retries is compatibility only. Removal is out of stage 1. Existing audit helper is not exhaustive. Local git clone failed DNS resolution; no local Docker executable. Connector access works. Do not claim complete local test run.
## Historical stage 1 next action (superseded)
Check CI on final code/doc commit, including new invariant tests. Native actual image UID/permissions, offline MegaLoc with verified assets, end-to-end syscall evidence and new lifecycle tests belong to stages 3–7. Remaining limitation: module-level review used relevant source excerpts for some large modules; no claim of exhaustive line-by-line review of all frontend/test/native code. Do not start stage 2 without user instruction.

## Commits and checks
- [dcea551](https://github.com/chapaayy/Sorter/commit/dcea5510ae0e601ee5bb74b113c3c10283378082): target category contract (45 categories), architecture, catalog, progress and test.
- [a11273e](https://github.com/chapaayy/Sorter/commit/a11273e6e58a45fc6af201727be6caf404f1d149), [426d97d](https://github.com/chapaayy/Sorter/commit/426d97d946a6f4e4a9fef5cf7618530f0f928937), [4021e64](https://github.com/chapaayy/Sorter/commit/4021e64b692ccc6796353d2874a4eb5aa6af6c3f): 43 pinned source files, 573 lexical candidates, zero failed fetches.
- [f777785](https://github.com/chapaayy/Sorter/commit/f7777851828272a99daf291a63bdd2ab752a444e): existing CI enabled for feature branch pushes, no jobs removed or weakened.
- [99e39c3](https://github.com/chapaayy/Sorter/commit/99e39c330d69f507786c6e7ee1e05891c9f7e0b2), [362112a](https://github.com/chapaayy/Sorter/commit/362112a288bc2b34d945fd29a99db1d68a67f791): all 35 SQL migration files indexed.
- JSON fetched from branch and parsed; 45 unique category IDs, mandatory string fields, 1132 MiB log budget, 3600s ZIP TTL, quotas disabled verified by connector-side checks. Not a pytest execution.
- [Feature CI 45444864314](https://github.com/chapaayy/Sorter/actions/runs/45444864314) was in progress at observation. Check newest SHA rather than assuming success.
- [Explicit remaining source scope](STORAGE_V2_REVIEW_BACKLOG.md). Do not close stage 1 on lexical evidence. Native runtime writes and full consumer graph still unverified.

## Continuation of stage 1
- [600a333](https://github.com/chapaayy/Sorter/commit/600a3337d482ff9a4a54ada871de8a84589e86a8): fix initial window scroll listener registration in VirtualThumbnailGrid. Prior [CI 45445156321](https://github.com/chapaayy/Sorter/actions/runs/45445156321) failed only mobile WebKit last virtual row of 150-photo gallery. Existing E2E kept. [Fix CI 45446230768](https://github.com/chapaayy/Sorter/actions/runs/45446230768) completed success on exact fix SHA.
- [42a4a57](https://github.com/chapaayy/Sorter/commit/42a4a5726f62e3fae8c3779904b4e4f750fe31fe): all 96 backlog modules fetched and mapped from source bodies/relevant excerpts.
- [9933060](https://github.com/chapaayy/Sorter/commit/9933060c723859a40313bb4003d8fb85bba22311): 573/573 original candidate lines assigned semantic dispositions; zero missing/duplicate entries in connector check.
- [57b3035](https://github.com/chapaayy/Sorter/commit/57b30359976eaed0d764a5e200d8096431bcbf3f): add six external categories, dependency review, coverage test, correct misleading ZIP finalization unit test to assert actual on-demand hook. Current commit also updates active documentation. Final CI must be checked on the actual branch head.

## Acceptance evidence and outstanding checks
- Branch/main checked against pinned base; main unchanged. No layout activation, old-data migration, deploy or merge.
- Connector invariant check on 0e527c2: 573 unique source candidates, 573 unique dispositions, zero missing or unknown category IDs; 96 expected/96 mapped modules, zero missing; 51 unique categories. This is independent of the pytest regression check.
- Backend job [138634360885](https://github.com/chapaayy/Sorter/actions/runs/45447264904/job/138634360885) on 57b3035 succeeded (318 passed, 28 subtests passed, one warning). [Full CI for 9933060](https://github.com/chapaayy/Sorter/actions/runs/45446789021) succeeded. [CI for 0e527c2](https://github.com/chapaayy/Sorter/actions/runs/45447428583) started; final conclusion not yet available when recorded. Check [latest branch Actions](https://github.com/chapaayy/Sorter/actions?query=branch%3Afeature%2Fstorage-architecture-v2) for the final SHA. No successful current-head conclusion is asserted here.
- Remaining decisions: canonical manifest/index and CSV demand; explicit historical reference retention policy (until resolved, retain dependencies); stable construction ID; reference abandonment TTL; lock namespace; image permissions and log owner; verified content model signature and working-model/cache separation; quota reserve default not agreed. Preserve unknown data, active leases, and published historical dependencies. No stage 2 started.
- Upstream MegaLoc inspected at 5fe0dd6; direct model constructor/forward does not explicitly download, hubconf entry point does; MAP uses direct loader. Browser resume/localStorage and gallery/download consumer dependencies recorded in dependency review. No actual model weights downloaded during audit.

## Stage 1 closure / stage 2 entry
Owner accepted stage 1 at a2645c7b5f3bfb3050e3976d68a85c0d0ed7d06c, [CI 45447879690](https://github.com/chapaayy/Sorter/actions/runs/45447879690), seven of seven jobs successful. No repeated global inventory. Mandatory acceptance gates transferred: stage 2 real non-root app UID, link/rename, path containment, clean bootstrap; stage 3 actual FFmpeg conversion and frame writes; stage 4 native thumbnail/embedding publication and dependency/pin checks; stage 5 native scratch/unnamed FD and offline verified MegaLoc after permitted cache removal; stage 6 actual image UID, PG/Caddy and infrastructure writes/permissions; stage 7 reconciliation and runtime write evidence. Stage 2 only; no migration of old data.

## Stage 2 implementation checkpoint
- [3ccc429](https://github.com/chapaayy/Sorter/commit/3ccc429bcdc2cdbf8b4449892e83cdb2d86f2a14): runtime policy loader, typed category keys and validation, dirfd-based safe read/stat/atomic publication, process-owned scratch and unit tests.
- Single application bind and config facade, protected directory bootstrap, version marker, Git/build exclusions, and real non-root Docker link/rename test added. Existing pipeline uses a transitional state subtree under the same app mount until stages 3–6 route producers to exact target category keys. This is not a second root. Infrastructure binds, updater, native model migration and bounded diagnostics remain later-stage work. Legacy automatic host observer is not launched by this installer. Stage 2 open: ownership, snapshot contract, installer tests and CI verification.

- [2854bb9](https://github.com/chapaayy/Sorter/commit/2854bb9ee22f93485e5398e3b75424215b96f849): single root activation. [CI 45450361701](https://github.com/chapaayy/Sorter/actions/runs/45450361701) backend failed because the mocked prerequisite fixture did not provide the new bootstrap boundary. Fixed fixture, added real bootstrap tests and immutable generated host root. No tests disabled. Full verification still pending.

- [94281e1](https://github.com/chapaayy/Sorter/commit/94281e1ba1f92d68298b58be1326b5a740a4c5d6): host root pinned in generated credentials, installer fixture and bootstrap tests. [a785ecc](https://github.com/chapaayy/Sorter/commit/a785eccd1582a22b77cd53767f76856e9139cea3): strict batch owner FK/index, authenticated creator, retry owner check and ownership tests. Follow-up adapts existing isolated SQL fixtures and hardens existing owned-path checks against internal symlink ancestors. Full CI and snapshot routing still open.

- [ebf0f40](https://github.com/chapaayy/Sorter/commit/ebf0f409a5bf4571662562205356ed36b94c4f22): existing SQL fixture ownership and stricter managed-path containment. Snapshot schema 2 now archives storage/app (canonical paths even for external configured storage root), layout marker and protected configuration, and verifies model/cache symlink boundaries. Actual full infrastructure backup and restore remain stage 6. [CI 45450138350](https://github.com/chapaayy/Sorter/actions/runs/45450138350) for foundation primitives succeeded 7/7; newer root/ownership commits require their own CI.
