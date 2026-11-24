# MAP Storage V2 progress
Branch: feature/storage-architecture-v2; base: c6d77ebb1c9c80c732df209a17a993dd38ec381f. Main read only. No deploy, migration of old data, or merge.
## Stage status
1. **IN PROGRESS** — branch created; baseline CI verified; initial architecture, category contract and catalog committed. Full semantic site review remains open; contract test execution and branch CI not verified yet.
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
Existing config and storage paths, compose, migrations 0001/0013/0024, update gate, archive compatibility service, audit write-site helper and key project docs inspected. AGENTS and PROJECT_MAP still describe prebuild/retry ZIP; actual archive_retries is compatibility only. Check all consumers before removal. Existing audit helper is not exhaustive. Local git clone failed DNS resolution; no local Docker executable. Connector access works. Do not claim complete local test run.
## Next action within stage 1
Finish exact pinned source review and file read/write/delete inventory, including SQL/JSON fields, native tools and frontend consumers; confirm historical retention and archive compatibility callers. Extend catalog and contract with any uncovered sites. Run/check contract tests and branch CI; only then close stage 1. No runtime changes before foundations.
