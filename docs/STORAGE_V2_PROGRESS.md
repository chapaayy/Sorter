# MAP Storage V2 progress
Branch: feature/storage-architecture-v2; base: c6d77ebb1c9c80c732df209a17a993dd38ec381f. Main read only. No deploy, migration of old data, or merge.
## Stage status
1. **IN PROGRESS** — branch created; baseline CI verified; initial architecture, category contract and catalog committed. 43 source files / 573 candidate lines indexed; 35 SQL migrations indexed. Full semantic site review remains open; branch CI has started, completion unverified.
2. Root and foundations — not started.
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
Existing config and storage paths, compose, database, migrations 0001–0036 (35 files), update gate, archive compatibility service, audit write-site helper and key project docs inspected for dependency evidence. See catalog and source/schema indexes; lexical candidates are not a semantic review. AGENTS and PROJECT_MAP still describe prebuild/retry ZIP; actual archive_retries is compatibility only. Check all consumers before removal. Existing audit helper is not exhaustive. Local git clone failed DNS resolution; no local Docker executable. Connector access works. Do not claim complete local test run.
## Next action within stage 1
Finish exact pinned source review and file read/write/delete inventory, including SQL/JSON fields, native tools and frontend consumers; confirm historical retention and archive compatibility callers. Extend catalog and contract with any uncovered sites. Run/check contract tests and branch CI; only then close stage 1. No runtime changes before foundations.

## Commits and checks
- [dcea551](https://github.com/chapaayy/Sorter/commit/dcea5510ae0e601ee5bb74b113c3c10283378082): target category contract (45 categories), architecture, catalog, progress and test.
- [a11273e](https://github.com/chapaayy/Sorter/commit/a11273e6e58a45fc6af201727be6caf404f1d149), [426d97d](https://github.com/chapaayy/Sorter/commit/426d97d946a6f4e4a9fef5cf7618530f0f928937), [4021e64](https://github.com/chapaayy/Sorter/commit/4021e64b692ccc6796353d2874a4eb5aa6af6c3f): 43 pinned source files, 573 lexical candidates, zero failed fetches.
- [f777785](https://github.com/chapaayy/Sorter/commit/f7777851828272a99daf291a63bdd2ab752a444e): existing CI enabled for feature branch pushes, no jobs removed or weakened.
- [99e39c3](https://github.com/chapaayy/Sorter/commit/99e39c330d69f507786c6e7ee1e05891c9f7e0b2), [362112a](https://github.com/chapaayy/Sorter/commit/362112a288bc2b34d945fd29a99db1d68a67f791): all 35 SQL migration files indexed.
- JSON fetched from branch and parsed; 45 unique category IDs, mandatory string fields, 1132 MiB log budget, 3600s ZIP TTL, quotas disabled verified by connector-side checks. Not a pytest execution.
- [Feature CI 45444864314](https://github.com/chapaayy/Sorter/actions/runs/45444864314) was in progress at observation. Check newest SHA rather than assuming success.
- [Explicit remaining source scope](STORAGE_V2_REVIEW_BACKLOG.md). Do not close stage 1 on lexical evidence. Native runtime writes and full consumer graph still unverified.
