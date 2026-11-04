# Agent instructions

1. **Do not change MegaLoc vectors, cosine threshold 0.50, grouping or SAM matching** without explicit approval and comparison with verified baseline. A refactor must preserve memberships and rankings.
2. Runtime must remain MegaLoc-only. Do not re-introduce DINO/CLIP/Qwen or old benchmark scripts.
3. Keep `Models/models/` and `Models/cache/` separate. Do not commit or delete weights, user photos, references, secrets or job history.
4. All server APIs should be authenticated except login and basic health; no arbitrary filesystem path may come from browser input.
5. PostgreSQL contains metadata, not blobs. Store original photos and numpy cache outside the container on persistent mounts.
6. Keep uploads resumable and idempotent by server-issued ID/offset. Reject traversal, ZIP slips, invalid images and incompatible cache entries.
7. Maintain separation: Caddy/TLS, API/DB, worker/CPU, library, frontend.
8. Keep root `.env` user-editable for DOMAIN only; never put admin or database passwords in committed files. Do not reset generated secrets on upgrade.
9. Use syntax/tests and Docker smoke tests when Docker is available. Update `README.md`, `PROJECT_MAP.md`, `FILE_INDEX.md` when changing topology or files.
10. GitHub workflow: implement in `vps/docker-rebuild` until deploy and real-photo regression are confirmed; do not merge an untested deployment into `main`.
