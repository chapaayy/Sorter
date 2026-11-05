# Future large-file transport: 4K/60 fps video

Status: **design only**. Video uploads are NOT enabled. This document does not change the existing MegaLoc photo pipeline.

## Goal

Allow authenticated browser uploads of 4K/60 fps recordings, commonly ~3 minutes and 1–2 GB per file, without buffering full files in browser JavaScript, Caddy, or FastAPI. Recover from network drops without retransmitting already acknowledged bytes.

## Existing baseline (photographs)

- Client: `PhotoSorter/frontend/src/utils/upload.ts`, ordered resumable PATCH requests in **16 MiB** chunks, and progress based on server-confirmed offsets.
- Concurrency: `PhotoSorter/frontend/src/stores/uploadSettings.ts`, **5 concurrent files by default**, configurable **1–10** in the Settings page; stored in the current browser.
- Server: `PhotoSorter/backend/server/uploads.py`, persistent upload session, `incoming/*.part` files, atomic finalization, SHA-256 and validation.
- Reverse proxy: Caddy per-request body limit **64 MB**, sufficient for 16 MiB PATCH. Do **not** send whole video files through the old direct PUT endpoint.
- **Current photo constraints must remain unchanged**: 60 MiB max/photo, allowed image extensions only, image verification by Pillow and thumbnail generation.

## Implementation requirements before enabling videos

1. **Transport and domain separation.** Extract reusable session/transfer logic that accepts an explicit file policy. Build a separate video/media upload route, storage namespace, database owner records, and authorization checks. Do not simply add `.mp4` to the current photo file allowlist: Pillow validation, MegaLoc jobs, and photo-thumbnail tasks are image-specific.
2. **Large-file-safe offsets.** Use signed 64-bit DB size/offset fields (verify existing schema/migrations and extend where necessary), safe integer offset arithmetic, bounded per-request buffers (~16 MiB), and server-enforced maximum per video (initial candidate: 4 GiB, configurable). Never allocate 1–2 GB buffers or read a whole video into memory.
3. **Resumability.** POST to create an upload, GET to inspect confirmed offset, PATCH an ordered chunk with `Upload-Offset`, POST to finalize; uploads are idempotent and survive browser refresh/restart. Detect conflicting metadata, short writes, duplicate chunks, stale sessions and files whose content has changed locally.
4. **Integrity and safe publication.** Verify size + streaming SHA-256 before atomic move from `.part` into a dedicated media directory; if the service crashes mid-finalization, retry safely. Account for free-space reserve, temporary files, disk quotas, cleanup of abandoned sessions, and per-user/session rate limits.
5. **Progress and failures.** Show *confirmed* transferred bytes, active file count, current/average MiB/s and Mbps, error retries and meaningful pause/resume behavior. Prefer 5 concurrent files to begin; a single 2 GB video should not require many simultaneous out-of-order requests. Adjustable concurrency must not bypass global server quotas.
6. **Background media processing.** Validate type by safe parsing, use `ffprobe` to check duration/resolution/codecs, and perform FFmpeg preview/transcoding **only in a separate worker after the upload is complete**. Do not block API uploads with 4K decoding/transcoding. Apply limits for duration/resolution and defend against malformed media.
7. **Testing.** Include synthetic 2 GiB sparse-file streaming tests, interrupted/retried PATCH, duplicate request, stale offset, 64-bit offsets, upload after browser restart, two large files in parallel, disk-full behavior, queue cancellation, and end-to-end browser tests. Compare throughput against the same photo/video data before and after changes.

## Suggested rollout

- Phase A: separate video upload/storage with resume, SHA-256, basic metadata, UI progress, quotas.
- Phase B: asynchronous preview/thumbnail, gallery, media retention and cleanup.
- Phase C: optional segmentation/processing or future ad-screen matching; independent of transport.

**Do not raise the old photo size limit, remove server validation, or add video to MegaLoc just to support uploads.**
