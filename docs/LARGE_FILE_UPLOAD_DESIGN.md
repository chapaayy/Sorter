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
3. **Resumability and speed for ONE large video.** Sequential PATCH/offset (used by photos) can stay as a compatibility path, but **a single 1–2 GB video must also be able to use several connections**. Create a media-specific multipart protocol: POST session with bounded chunk size (start with 16 MiB); PUT indexed parts with explicit byte ranges and optional per-part hash; GET a persisted completed-part bitmap; POST finalize only after all parts are present. Allow 2–5 in-flight parts for one file within a shared concurrency budget. Implement server-side random-access writes/preallocation safely, with a **per-part lock** instead of one full-file lock, atomic part completion metadata, no overlapping writes, and crash-resumable status. Handle conflicting metadata, duplicate/retried parts, short writes and a changed local file. This matters because 5 parallel *files* do not accelerate a folder containing exactly one large video.
4. **Integrity and safe publication.** Verify size + streaming SHA-256 before atomic move from `.part` into a dedicated media directory; if the service crashes mid-finalization, retry safely. Account for free-space reserve, temporary files, disk quotas, cleanup of abandoned sessions, and per-user/session rate limits.
5. **Progress and failures.** Show *confirmed* transferred bytes, active files/parts, current/average MiB/s and Mbps, retries and real pause/resume. Use a total in-flight part/request budget (initial default 5, configurable), allocate it fairly between files and parts, and cap per-file part concurrency to avoid disk thrash and excessive browser connections. Browsers often cap HTTP/1.1 connections per origin; verify measured benefits with actual uploads before increasing the ceiling. Adjustable concurrency must not bypass global server quotas.
6. **Background media processing.** Validate type by safe parsing, use `ffprobe` to check duration/resolution/codecs, and perform FFmpeg preview/transcoding **only in a separate worker after the upload is complete**. Do not block API uploads with 4K decoding/transcoding. Apply limits for duration/resolution and defend against malformed media.
7. **Testing.** Include synthetic 2 GiB sparse-file streaming tests, reordered/duplicate/retried PUT parts, interrupted single-video multipart upload, a missing part before finalize, concurrent non-overlapping writes, 64-bit offsets, upload after browser restart, two large files in parallel, disk-full behavior, queue cancellation, and end-to-end browser tests. Compare **one 2 GB video** transferred with 1 versus 2–5 simultaneous parts, as well as the same photo dataset before/after changes.

## Suggested rollout

- Phase A: separate video upload/storage with multipart parallel parts for a single video, resume, SHA-256, basic metadata, UI progress, quotas.
- Phase B: asynchronous preview/thumbnail, gallery, media retention and cleanup.
- Phase C: optional segmentation/processing or future ad-screen matching; independent of transport.

**Do not raise the old photo size limit, remove server validation, or add video to MegaLoc just to support uploads.**
