# Deployment and operations

- DNS A/AAAA must point to the VPS; if AAAA is configured, IPv6 must also work. Open TCP ports 80 and 443 and optionally UDP 443.
- Install Docker Engine + Compose v2. Use the root `install.sh`; it creates a private `.env.generated` with credentials and starts all four services.
- Caddy automatically issues HTTPS certs. TLS state: `caddy_data`, `caddy_config`. Do not remove volumes during an upgrade.
- First model install can be done through the Web UI. Download and verification logs go under `Models/cache/downloads/`.
- Data/weights are persistent bind mounts; PostgreSQL uses `postgres_data`. The app image is immutable; no `pip install` on startup.
- Backup at least `postgres_data` (via `pg_dump`), `PhotoSorter/data/references`, `PhotoSorter/data/uploads`, `PhotoSorter/data/runs`, `PhotoSorter/data/outputs` and `.env.generated`. Also preserve `Models/models` to avoid reinstalling large weights. Reference cache can be recomputed, but should be backed up if possible.
- `docker compose ... logs -f worker`, `logs -f api`, `logs -f caddy` show service logs. Browser logs and statuses are persisted per run.
- Never change SAM folders midway through a run. The API rejects reference mutation while a job is active.
- No automated file deletion/retention is enabled. Monitor 200 GB disk use and schedule a retention policy before daily production use.
- Limit to a single API replica because the file-upload lock is process-local. Scaling API/Worker horizontally requires distributed upload locks, updated queue coordination, and storage semantics.
- The browser currently accepts directories for FO and references. ZIP upload of references and account password rotation are future enhancements, not implemented yet.
- Before production, deploy to staging and run a representative A/B test against 189 FO baseline (27 groups, three uncertain photos), plus large-photo resumable uploads and TLS/backup recovery checks.
