# Stage 1 semantic disposition of existing 573 candidate lines

Baseline c6d77ebb1c9c80c732df209a17a993dd38ec381f. Each candidate from the three existing lexical indexes has one reviewed disposition; groups of lines sharing an operation use the same explanation. `config`, `non-file`, DB metadata, socket, and test entries are distinguished from actual disk writes. This is source-level evidence, not runtime tracing. Native libraries and indirect operations beyond those candidates are documented separately; stage-specific implementation/tests remain required. No source code or user data modified by the audit.

## `PhotoSorter/backend/server/uploads.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 3 | config | fo_upload_part, fo_original | Imports/process API and legacy root declarations; not writes themselves. |
| 18 | config | fo_upload_part, fo_original | Imports/process API and legacy root declarations; not writes themselves. |
| 22 | config | fo_upload_part, fo_original | Imports/process API and legacy root declarations; not writes themselves. |
| 23 | config | fo_upload_part, fo_original | Imports/process API and legacy root declarations; not writes themselves. |
| 78 | create | fo_upload_part | Create part under incoming for registered transfer; resume touches existing or creates missing part. |
| 79 | create | fo_upload_part | Create part under incoming for registered transfer; resume touches existing or creates missing part. |
| 105 | create | fo_upload_part | Create part under incoming for registered transfer; resume touches existing or creates missing part. |
| 106 | create | fo_upload_part | Create part under incoming for registered transfer; resume touches existing or creates missing part. |
| 107 | stat | fo_upload_part | Actual length for resume/offset; DB received not sole authority. |
| 125 | stat | fo_upload_part | Actual length for resume/offset; DB received not sole authority. |
| 132 | write/rollback | fo_upload_part | Open r+b, append chunk, truncate to prior actual offset on failure. |
| 140 | write/rollback | fo_upload_part | Open r+b, append chunk, truncate to prior actual offset on failure. |
| 143 | write/rollback | fo_upload_part | Open r+b, append chunk, truncate to prior actual offset on failure. |
| 200 | read/DB | fo_upload_part, fo_original | Idempotent finalized target_path, size/digest read, validation exception and locked current state recheck. |
| 202 | read/DB | fo_upload_part, fo_original | Idempotent finalized target_path, size/digest read, validation exception and locked current state recheck. |
| 205 | read/DB | fo_upload_part, fo_original | Idempotent finalized target_path, size/digest read, validation exception and locked current state recheck. |
| 207 | read/DB | fo_upload_part, fo_original | Idempotent finalized target_path, size/digest read, validation exception and locked current state recheck. |
| 221 | read/DB | fo_upload_part, fo_original | Idempotent finalized target_path, size/digest read, validation exception and locked current state recheck. |
| 232 | read/DB | fo_upload_part, fo_original | Idempotent finalized target_path, size/digest read, validation exception and locked current state recheck. |
| 235 | read/DB | fo_upload_part, fo_original | Idempotent finalized target_path, size/digest read, validation exception and locked current state recheck. |
| 237 | publish | fo_original | Create destination, verify existing target digest or link part, persist checksum/path; source name must become UUID key. |
| 244 | publish | fo_original | Create destination, verify existing target digest or link part, persist checksum/path; source name must become UUID key. |
| 249 | publish | fo_original | Create destination, verify existing target digest or link part, persist checksum/path; source name must become UUID key. |
| 252 | publish | fo_original | Create destination, verify existing target digest or link part, persist checksum/path; source name must become UUID key. |
| 262 | delete | fo_upload_part | After finalize commit remove part link, not original. |
| 321 | DB read | fo_original | Returns finalized path for idempotency; remove exposed absolute path in new contract only after API consumers checked. |
| 360 | delete | fo_upload_part | Cancel unfinished transfer; unlink generated part. |
| 365 | delete | fo_upload_part | Cancel unfinished transfer; unlink generated part. |

## `PhotoSorter/backend/server/database.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 14 | DB schema | postgres_data | Users/sessions/batches/uploads rows; no Python file operation; PG writes native pages/WAL. |
| 21 | DB schema | postgres_data | Users/sessions/batches/uploads rows; no Python file operation; PG writes native pages/WAL. |
| 26 | DB schema | postgres_data | Users/sessions/batches/uploads rows; no Python file operation; PG writes native pages/WAL. |
| 30 | DB schema | postgres_data | Users/sessions/batches/uploads rows; no Python file operation; PG writes native pages/WAL. |
| 40 | DB path | fo_original, reference_gallery | uploads.target_path typed key conversion. |
| 44 | DB schema | run_state, postgres_data | Jobs snapshot and FK; DB authoritative. |
| 54 | DB path | reference_embedding | Cache composite key and cache_path; no direct file write. |
| 57 | DB path | reference_embedding | Cache composite key and cache_path; no direct file write. |

## `PhotoSorter/backend/server/jobs.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 8 | path/DB | run_state, fo_original, result_media | Snapshot legacy new_photos and output root; queued path fields are not physical creation. |
| 117 | path/DB | run_state, fo_original, result_media | Snapshot legacy new_photos and output root; queued path fields are not physical creation. |
| 118 | path/DB | run_state, fo_original, result_media | Snapshot legacy new_photos and output root; queued path fields are not physical creation. |
| 184 | delegate | run_state | ServerJob.save calls base save_run, then DB snapshot; eliminate redundant state only after readers. |
| 185 | delegate | run_state | ServerJob.save calls base save_run, then DB snapshot; eliminate redundant state only after readers. |

## `PhotoSorter/backend/server/services/batches.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 10 | config | fo_upload_part | Imported root. |
| 146 | read | fo_upload_part | Check real partial size and hash prefix for resume. |
| 151 | read | fo_upload_part | Check real partial size and hash prefix for resume. |
| 159 | read | fo_upload_part | Check real partial size and hash prefix for resume. |
| 176 | non-file | postgres_data | rename is SQL display metadata, not filesystem rename. |
| 208 | delete | fo_original | Owned path; shared-path query before unlink; keep original if other upload references same path. |
| 209 | delete | fo_original | Owned path; shared-path query before unlink; keep original if other upload references same path. |
| 210 | delete | fo_original | Owned path; shared-path query before unlink; keep original if other upload references same path. |
| 211 | delete | fo_original | Owned path; shared-path query before unlink; keep original if other upload references same path. |
| 213 | delete | fo_upload_part | Generated UUID part only. |
| 214 | delete | fo_upload_part | Generated UUID part only. |
| 216 | delete | fo_normalized | Owned media_output_path remove with source. |

## `PhotoSorter/backend/server/storage/batch_cleanup.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 8 | path | result_media, result_metadata, run_state, run_log, zip_results, zip_construction | Run directories derived from IDs, current nested archives and logs included. |
| 13 | path | result_media, result_metadata, run_state, run_log, zip_results, zip_construction | Run directories derived from IDs, current nested archives and logs included. |
| 21 | open directory | fo_original, fo_normalized | NOFOLLOW directory fd for safe removal. |
| 31 | delete | result_media, result_metadata, run_state, run_log, fo_upload_part, zip_results, zip_construction, processing_staging | Remove run trees and generated upload parts, no shared refs. |
| 35 | delete | result_media, result_metadata, run_state, run_log, fo_upload_part, zip_results, zip_construction, processing_staging | Remove run trees and generated upload parts, no shared refs. |
| 41 | stat/delete | fo_original, fo_normalized | Use dir_fd stat nofollow, rmtree/unlink entries, remove empty batch directory; preserve ownership checks. |
| 43 | stat/delete | fo_original, fo_normalized | Use dir_fd stat nofollow, rmtree/unlink entries, remove empty batch directory; preserve ownership checks. |
| 45 | stat/delete | fo_original, fo_normalized | Use dir_fd stat nofollow, rmtree/unlink entries, remove empty batch directory; preserve ownership checks. |
| 50 | stat/delete | fo_original, fo_normalized | Use dir_fd stat nofollow, rmtree/unlink entries, remove empty batch directory; preserve ownership checks. |

## `PhotoSorter/backend/server/storage/reference_objects.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 15 | config | reference_object, reference_gallery, reference_upload_part | Roots; LEGACY_ROOT for existing gallery, no production dual layout in v2. |
| 18 | config | reference_object, reference_gallery, reference_upload_part | Roots; LEGACY_ROOT for existing gallery, no production dual layout in v2. |
| 19 | config | reference_object, reference_gallery, reference_upload_part | Roots; LEGACY_ROOT for existing gallery, no production dual layout in v2. |
| 42 | read | reference_object, reference_upload_part | Verify trusted path/size and digest bytes. |
| 47 | read | reference_object, reference_upload_part | Verify trusted path/size and digest bytes. |
| 65 | create | reference_upload_part | Safe directory creation and exclusive part open. |
| 76 | create | reference_upload_part | Safe directory creation and exclusive part open. |
| 88 | stat/write | reference_upload_part | Validate offset, write append and fsync. |
| 97 | stat/write | reference_upload_part | Validate offset, write append and fsync. |
| 103 | stat/write | reference_upload_part | Validate offset, write append and fsync. |
| 105 | stat/write | reference_upload_part | Validate offset, write append and fsync. |
| 110 | read | reference_upload_part | PIL verifies image; no output. |
| 130 | publish | reference_object | Hardlink staged part to final session file; new content-addressed object. |
| 143 | delete | reference_upload_part | Unlink only committed partial. |

## `PhotoSorter/backend/server/storage/thumbnail_cache.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 5 | config | fo_thumbnail, reference_thumbnail | Global cache root; actual key construction and safety helpers; split per owner/shared. |
| 11 | config | fo_thumbnail, reference_thumbnail | Global cache root; actual key construction and safety helpers; split per owner/shared. |

## `PhotoSorter/backend/server/reference_cache.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 12 | config | reference_object, reference_embedding | Roots; protected embedding cache. |
| 16 | config | reference_object, reference_embedding | Roots; protected embedding cache. |
| 17 | config | reference_object, reference_embedding | Roots; protected embedding cache. |
| 21 | DB/read | reference_embedding | Resolve cached path, np.load allow_pickle=False, finite 1d check; no write. |
| 24 | DB/read | reference_embedding | Resolve cached path, np.load allow_pickle=False, finite 1d check; no write. |
| 28 | DB/read | reference_embedding | Resolve cached path, np.load allow_pickle=False, finite 1d check; no write. |
| 29 | DB/read | reference_embedding | Resolve cached path, np.load allow_pickle=False, finite 1d check; no write. |
| 46 | create | reference_embedding | Ensure cache directory. |
| 63 | read | reference_object | Digest reference bytes; cache key. |
| 83 | write/publish | reference_embedding, atomic_fragment | NPY float32 in temp, replace, upsert DB, cleanup fragment; path/signature validation and GC dependency needed. |
| 84 | write/publish | reference_embedding, atomic_fragment | NPY float32 in temp, replace, upsert DB, cleanup fragment; path/signature validation and GC dependency needed. |
| 86 | write/publish | reference_embedding, atomic_fragment | NPY float32 in temp, replace, upsert DB, cleanup fragment; path/signature validation and GC dependency needed. |
| 88 | write/publish | reference_embedding, atomic_fragment | NPY float32 in temp, replace, upsert DB, cleanup fragment; path/signature validation and GC dependency needed. |
| 90 | write/publish | reference_embedding, atomic_fragment | NPY float32 in temp, replace, upsert DB, cleanup fragment; path/signature validation and GC dependency needed. |

## `PhotoSorter/backend/server/workers/media_prepare.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 7 | config | fo_normalized, transcode_temp | Imports only. |
| 12 | config | fo_normalized, transcode_temp | Imports only. |
| 41 | DB/path/create | fo_original, fo_normalized | Load source path, create normalized directory. |
| 45 | DB/path/create | fo_original, fo_normalized | Load source path, create normalized directory. |
| 48 | DB/path/create | fo_original, fo_normalized | Load source path, create normalized directory. |
| 56 | read | fo_original | ffprobe source read; exception type no write. |
| 57 | read | fo_original | ffprobe source read; exception type no write. |
| 88 | delete | transcode_temp | Clear partial before attempt. |
| 92 | stat/read | fo_original, transcode_temp | Owned source; disk guard based on source size. |
| 93 | stat/read | fo_original, transcode_temp | Owned source; disk guard based on source size. |
| 94 | stat/read | fo_original, transcode_temp | Owned source; disk guard based on source size. |
| 100 | publish | transcode_temp, fo_normalized | Fsync partial, replace final normalized output. |
| 102 | publish | transcode_temp, fo_normalized | Fsync partial, replace final normalized output. |
| 110 | delete | transcode_temp | Finally removes partial, original remains. |

## `PhotoSorter/backend/server/media/video.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 4 | non-file | scratch | Import only. |
| 30 | native temp/write | scratch | Unnamed error and progress files, Popen writes via fd; close and kill/wait on error; explicit dir required. |
| 32 | native temp/write | scratch | Unnamed error and progress files, Popen writes via fd; close and kill/wait on error; explicit dir required. |
| 33 | native temp/write | scratch | Unnamed error and progress files, Popen writes via fd; close and kill/wait on error; explicit dir required. |
| 86 | native temp/write | scratch | ffprobe writes frame timestamp index to unnamed fd, bounded 16 MiB check. |
| 91 | native temp/write | scratch | ffprobe writes frame timestamp index to unnamed fd, bounded 16 MiB check. |
| 151 | read | video_frames | Enumerate JPEG output created by ffmpeg -frames:v, no write here. |

## `PhotoSorter/backend/app/results/exporter.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 15 | atomic write | atomic_fragment, run_state, result_metadata | Create parent, adjacent mkstemp, write JSON, replace and unlink fragment; called for run state, index and manifest. |
| 18 | atomic write | atomic_fragment, run_state, result_metadata | Create parent, adjacent mkstemp, write JSON, replace and unlink fragment; called for run state, index and manifest. |
| 22 | atomic write | atomic_fragment, run_state, result_metadata | Create parent, adjacent mkstemp, write JSON, replace and unlink fragment; called for run state, index and manifest. |
| 25 | atomic write | atomic_fragment, run_state, result_metadata | Create parent, adjacent mkstemp, write JSON, replace and unlink fragment; called for run state, index and manifest. |
| 32 | atomic write | atomic_fragment, run_state, result_metadata | Create parent, adjacent mkstemp, write JSON, replace and unlink fragment; called for run state, index and manifest. |
| 38 | write | result_metadata, processing_staging | Write JSONL and CSV in staging; both additional to manifest.json. |
| 40 | write | result_metadata, processing_staging | Write JSONL and CSV in staging; both additional to manifest.json. |
| 41 | write | result_metadata, processing_staging | Write JSONL and CSV in staging; both additional to manifest.json. |

## `PhotoSorter/backend/app/results/repository.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 4 | config/path | run_state | RUNS_DIR validated run path. |
| 11 | config/path | run_state | RUNS_DIR validated run path. |
| 18 | read/list | run_state | Read run.json and iterate run dirs. |
| 22 | read/list | run_state | Read run.json and iterate run dirs. |
| 23 | read/list | run_state | Read run.json and iterate run dirs. |
| 31 | create/delete | processing_staging | Create output parent and clear old unpublished staging. |
| 34 | create/delete | processing_staging | Create output parent and clear old unpublished staging. |
| 50 | publish/delete | processing_staging, result_media, result_metadata | Rename complete staging to model output or delete only failed staging. |
| 52 | publish/delete | processing_staging, result_media, result_metadata | Rename complete staging to model output or delete only failed staging. |
| 55 | create | run_state | Create model index dir, then atomic_json index points to manifest. |
| 65 | read | run_state, result_metadata | Read index JSON and manifest path; both readers migrate together. |
| 66 | read | run_state, result_metadata | Read index JSON and manifest path; both readers migrate together. |

## `PhotoSorter/backend/app/jobs/runtime.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 23 | delegate | run_state | save_run writes run.json; running transition calls save. |
| 42 | delegate | run_state | save_run writes run.json; running transition calls save. |
| 60 | write | run_log | errors.txt traceback, separate unbounded-by-events file; move into bounded log policy. |
| 67 | delegate | run_state, run_log | Final save and event log. |

## `PhotoSorter/backend/server/services/archive_cache.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 24 | directory/lock | archive_lock | Pin cache directory via shared flock; no separate lock file here. |
| 25 | directory/lock | archive_lock | Pin cache directory via shared flock; no separate lock file here. |
| 27 | directory/lock | archive_lock | Pin cache directory via shared flock; no separate lock file here. |
| 48 | directory/lock/stat | archive_lock | Root directory exclusive flock serializes archive admission; statvfs check. |
| 50 | directory/lock/stat | archive_lock | Root directory exclusive flock serializes archive admission; statvfs check. |
| 51 | directory/lock/stat | archive_lock | Root directory exclusive flock serializes archive admission; statvfs check. |
| 62 | directory/lock/stat | zip_results, zip_construction, zip_references, zip_fragment, archive_lock | Open folder NOFOLLOW, nonblocking exclusive, stat recognized regular file. |
| 69 | directory/lock/stat | zip_results, zip_construction, zip_references, zip_fragment, archive_lock | Open folder NOFOLLOW, nonblocking exclusive, stat recognized regular file. |
| 76 | directory/lock/stat | zip_results, zip_construction, zip_references, zip_fragment, archive_lock | Open folder NOFOLLOW, nonblocking exclusive, stat recognized regular file. |
| 85 | read/delete | zip_results, zip_construction, zip_references, zip_fragment, archive_lock | Keep lock if ZIP exists; unlink only recognized expired file with no pin. |
| 89 | read/delete | zip_results, zip_construction, zip_references, zip_fragment, archive_lock | Keep lock if ZIP exists; unlink only recognized expired file with no pin. |

## `PhotoSorter/backend/server/services/archives.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 35 | path/stat | result_media, zip_results, zip_construction | Derive run and inspect existing ZIP file validity/freshness. |
| 55 | path/stat | result_media, zip_results, zip_construction | Derive run and inspect existing ZIP file validity/freshness. |
| 60 | create/lock | archive_lock, zip_results, zip_construction | Create .archives dir, sum source size, pin folder, create stable per-key lock and take exclusive flock. |
| 62 | create/lock | archive_lock, zip_results, zip_construction | Create .archives dir, sum source size, pin folder, create stable per-key lock and take exclusive flock. |
| 68 | create/lock | archive_lock, zip_results, zip_construction | Create .archives dir, sum source size, pin folder, create stable per-key lock and take exclusive flock. |
| 70 | create/lock | archive_lock, zip_results, zip_construction | Create .archives dir, sum source size, pin folder, create stable per-key lock and take exclusive flock. |
| 71 | create/lock | archive_lock, zip_results, zip_construction | Create .archives dir, sum source size, pin folder, create stable per-key lock and take exclusive flock. |
| 79 | delete/unlock | zip_results, zip_construction, archive_lock | Discard invalid cached ZIP while protected, release key lock. |
| 83 | delete/unlock | zip_results, zip_construction, archive_lock | Discard invalid cached ZIP while protected, release key lock. |
| 86 | write | zip_fragment, result_media | mkstemp, ZIP_STORED stream selected result paths, fsync. |
| 89 | write | zip_fragment, result_media | mkstemp, ZIP_STORED stream selected result paths, fsync. |
| 97 | write | zip_fragment, result_media | mkstemp, ZIP_STORED stream selected result paths, fsync. |
| 98 | write | zip_fragment, result_media | mkstemp, ZIP_STORED stream selected result paths, fsync. |
| 101 | write | zip_fragment, result_media | mkstemp, ZIP_STORED stream selected result paths, fsync. |
| 104 | verify/publish/delete | zip_fragment, zip_results, zip_construction | Read ZIP verification then replace final, finally remove temp. |
| 112 | verify/publish/delete | zip_fragment, zip_results, zip_construction | Read ZIP verification then replace final, finally remove temp. |
| 115 | verify/publish/delete | zip_fragment, zip_results, zip_construction | Read ZIP verification then replace final, finally remove temp. |

## `PhotoSorter/backend/server/services/reference_imports.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 121 | delegate/read | reference_object | Verify matching published object path+digest for dedup. Other transfer writes delegated outside lexical hits. |

## `PhotoSorter/backend/server/services/reference_uploads.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 26 | delegate/read | reference_object | Verify current matching member before duplicate acknowledgment. |
| 83 | read | reference_upload_part | Digest completed part; finalize delegates object publication and cleanup. |

## `PhotoSorter/backend/server/services/reference_publication.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 15 | non-file | postgres_data | Canonical manifest digest computed in RAM from members/model signature. |
| 18 | non-file | postgres_data | Canonical manifest digest computed in RAM from members/model signature. |
| 24 | delegate/read | reference_object | Verify immutable member path, size, hash. |
| 31 | DB | postgres_data | Current pointer lock, initial members/initial version checks; no file output. |
| 35 | DB | postgres_data | Current pointer lock, initial members/initial version checks; no file output. |
| 37 | DB | postgres_data | Current pointer lock, initial members/initial version checks; no file output. |
| 39 | DB | postgres_data | Current pointer lock, initial members/initial version checks; no file output. |
| 47 | DB | postgres_data | Current pointer lock, initial members/initial version checks; no file output. |
| 51 | DB | postgres_data | Current pointer lock, initial members/initial version checks; no file output. |
| 59 | DB | postgres_data, reference_object | Publish version/members/target_path and advance pointer atomically; metadata pin, not bytes write. |
| 66 | DB | postgres_data, reference_object | Publish version/members/target_path and advance pointer atomically; metadata pin, not bytes write. |
| 74 | DB | postgres_data, reference_object | Publish version/members/target_path and advance pointer atomically; metadata pin, not bytes write. |
| 76 | DB | postgres_data, reference_object | Publish version/members/target_path and advance pointer atomically; metadata pin, not bytes write. |
| 80 | DB | postgres_data, reference_object | Publish version/members/target_path and advance pointer atomically; metadata pin, not bytes write. |
| 81 | DB | postgres_data, reference_object | Publish version/members/target_path and advance pointer atomically; metadata pin, not bytes write. |
| 84 | DB | postgres_data, reference_object | Publish version/members/target_path and advance pointer atomically; metadata pin, not bytes write. |
| 86 | DB | postgres_data, reference_object | Publish version/members/target_path and advance pointer atomically; metadata pin, not bytes write. |
| 100 | DB path | run_state, reference_object | Return pinned path/hash snapshot used by FO inference. |

## `PhotoSorter/backend/server/services/reference_gallery.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 9 | config | reference_gallery | Gallery root. |
| 14 | config | reference_gallery | Gallery root. |
| 20 | create/link | reference_gallery, reference_object | Create SAM dir, hardlink immutable source to display projection. |
| 27 | create/link | reference_gallery, reference_object | Create SAM dir, hardlink immutable source to display projection. |
| 36 | DB path | reference_gallery | Store gallery target_path in uploads. |

## `PhotoSorter/backend/server/db/repositories/reference_versions.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 7 | DB read | postgres_data, reference_object | Current version and member queries; target_path/signature dependency, no file writes. |
| 9 | DB read | postgres_data, reference_object | Current version and member queries; target_path/signature dependency, no file writes. |
| 15 | DB read | postgres_data, reference_object | Current version and member queries; target_path/signature dependency, no file writes. |
| 16 | DB read | postgres_data, reference_object | Current version and member queries; target_path/signature dependency, no file writes. |

## `PhotoSorter/backend/server/services/thumbnail_gc.py`

Zero lexical hits; collect delegates gc_unowned and gc_incomplete, actual deletes in thumbnails.

## `PhotoSorter/backend/server/services/thumbnails.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 13 | config | fo_thumbnail, reference_thumbnail | Root import. |
| 31 | DB/read path | fo_original, reference_gallery | Claim joins upload fields, check owned source root (SAM path on refs). Rename-related old gallery roots need stable key. |
| 46 | DB/read path | fo_original, reference_gallery | Claim joins upload fields, check owned source root (SAM path on refs). Rename-related old gallery roots need stable key. |
| 47 | DB/read path | fo_original, reference_gallery | Claim joins upload fields, check owned source root (SAM path on refs). Rename-related old gallery roots need stable key. |
| 48 | DB/read path | fo_original, reference_gallery | Claim joins upload fields, check owned source root (SAM path on refs). Rename-related old gallery roots need stable key. |
| 57 | create | atomic_fragment | Destination parent and adjacent unique WebP fragment. |
| 58 | create | atomic_fragment | Destination parent and adjacent unique WebP fragment. |
| 61 | read | fo_original, reference_gallery | PIL decode, load to RAM. |
| 62 | read | fo_original, reference_gallery | PIL decode, load to RAM. |
| 86 | write/publish/delete | fo_thumbnail, reference_thumbnail, atomic_fragment | Save WebP through file fd, fsync, replace, finally unlink fragment. |
| 88 | write/publish/delete | fo_thumbnail, reference_thumbnail, atomic_fragment | Save WebP through file fd, fsync, replace, finally unlink fragment. |
| 90 | write/publish/delete | fo_thumbnail, reference_thumbnail, atomic_fragment | Save WebP through file fd, fsync, replace, finally unlink fragment. |
| 93 | write/publish/delete | fo_thumbnail, reference_thumbnail, atomic_fragment | Save WebP through file fd, fsync, replace, finally unlink fragment. |
| 105 | native temp | scratch | TemporaryDirectory for video poster; FFmpeg creates JPEG there. |
| 154 | scan/delete | fo_thumbnail, reference_thumbnail | Enumerate WebP, grace and DB ownership recheck, delete orphan only. |
| 158 | scan/delete | fo_thumbnail, reference_thumbnail | Enumerate WebP, grace and DB ownership recheck, delete orphan only. |
| 166 | scan/delete | fo_thumbnail, reference_thumbnail | Enumerate WebP, grace and DB ownership recheck, delete orphan only. |
| 175 | scan/delete | atomic_fragment | Stale .thumb temp cleanup, require lease-safe behavior in v2. |
| 180 | scan/delete | atomic_fragment | Stale .thumb temp cleanup, require lease-safe behavior in v2. |
| 181 | scan/delete | atomic_fragment | Stale .thumb temp cleanup, require lease-safe behavior in v2. |

## `PhotoSorter/backend/server/services/reference_archives.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 21 | config | zip_references | Export root. |
| 30 | config | zip_references | Export root. |
| 52 | read path | reference_object | Current member target path for archive plan. |
| 99 | create/lock | archive_lock | Create export dir, pin and key lock. |
| 105 | create/lock | archive_lock | Create export dir, pin and key lock. |
| 106 | create/lock | archive_lock | Create export dir, pin and key lock. |
| 112 | delete/unlock | zip_references, archive_lock | Discard invalid ZIP, release key lock. |
| 121 | delete/unlock | zip_references, archive_lock | Discard invalid ZIP, release key lock. |
| 125 | write | zip_fragment, reference_object | Create temp file, ZIP_STORED source bytes and fsync. |
| 128 | write | zip_fragment, reference_object | Create temp file, ZIP_STORED source bytes and fsync. |
| 132 | write | zip_fragment, reference_object | Create temp file, ZIP_STORED source bytes and fsync. |
| 134 | write | zip_fragment, reference_object | Create temp file, ZIP_STORED source bytes and fsync. |
| 135 | verify/publish/delete | zip_fragment, zip_references | Verify archive, replace, finally unlink fragment. |
| 140 | verify/publish/delete | zip_fragment, zip_references | Verify archive, replace, finally unlink fragment. |
| 143 | verify/publish/delete | zip_fragment, zip_references | Verify archive, replace, finally unlink fragment. |

## `PhotoSorter/backend/server/services/temp_cleanup.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 4 | config | fo_upload_part | Incoming root only. |
| 8 | config | fo_upload_part | Incoming root only. |
| 32 | stat/delete | fo_upload_part | 30d age + DB row/batch lease/job checks; delete partial; not finalized originals. |
| 33 | stat/delete | fo_upload_part | 30d age + DB row/batch lease/job checks; delete partial; not finalized originals. |

## `PhotoSorter/backend/server/workers/cleanup.py`

Zero lexical hits; run_cycle archive_cache.collect, retention, reconcile_incomplete_exports, temp_cleanup and thumbnail_gc; independent deletion thread; stdout.

## `PhotoSorter/backend/app/system/model_store.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 12 | config | model_metadata | Verification marker location in downloads cache; legacy fallback remove at stage 5. |
| 18 | config | model_metadata | Verification marker location in downloads cache; legacy fallback remove at stage 5. |
| 19 | config | model_metadata | Verification marker location in downloads cache; legacy fallback remove at stage 5. |
| 25 | path read | model_source, model_weights, technical_cache | Dedup and search torch/hf roots including HOME legacy fallback; actual dependencies not all disposable. |
| 31 | path read | model_source, model_weights, technical_cache | Dedup and search torch/hf roots including HOME legacy fallback; actual dependencies not all disposable. |
| 43 | path read | model_source, model_weights, technical_cache | Dedup and search torch/hf roots including HOME legacy fallback; actual dependencies not all disposable. |
| 47 | create/env | technical_cache | Create Torch and HF dirs, set env; loader offline. |
| 48 | create/env | technical_cache | Create Torch and HF dirs, set env; loader offline. |
| 49 | create/env | technical_cache | Create Torch and HF dirs, set env; loader offline. |
| 50 | create/env | technical_cache | Create Torch and HF dirs, set env; loader offline. |
| 59 | path/stat | model_source, model_weights | Select source repo and checkpoint including HF snapshots. |
| 63 | path/stat | model_source, model_weights | Select source repo and checkpoint including HF snapshots. |
| 66 | path/stat | model_source, model_weights | Select source repo and checkpoint including HF snapshots. |
| 73 | path/stat | model_source, model_weights | Select source repo and checkpoint including HF snapshots. |
| 85 | read/hash | model_weights, model_source | Weight stat and source Python content hash; current signature includes absolute path/mtime, new signature needs verified content. |
| 87 | read/hash | model_weights, model_source | Weight stat and source Python content hash; current signature includes absolute path/mtime, new signature needs verified content. |
| 89 | read/hash | model_weights, model_source | Weight stat and source Python content hash; current signature includes absolute path/mtime, new signature needs verified content. |
| 97 | read | model_metadata | Read verification marker. |
| 105 | write/publish | model_metadata, atomic_fragment | Create marker parent, write .tmp and replace. |
| 107 | write/publish | model_metadata, atomic_fragment | Create marker parent, write .tmp and replace. |
| 108 | write/publish | model_metadata, atomic_fragment | Create marker parent, write .tmp and replace. |

## `PhotoSorter/backend/app/system/downloads.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 5 | config | model_download, service_log | Imports and LOG_DIR; current mixes logs/temp. |
| 12 | config | model_download, service_log | Imports and LOG_DIR; current mixes logs/temp. |
| 15 | config | model_download, service_log | Imports and LOG_DIR; current mixes logs/temp. |
| 19 | stat | model_download, model_weights | Measure target apparent file sizes for progress. |
| 21 | stat | model_download, model_weights | Measure target apparent file sizes for progress. |
| 51 | create | service_log, model_weights | Log dir and weight target dir. |
| 66 | create | service_log, model_weights | Log dir and weight target dir. |
| 67 | create | service_log, model_weights | Log dir and weight target dir. |
| 73 | env/create | technical_cache, model_download | Configure HOME/XDG/HF/Xet/Torch; mkdir provider cache dirs; os.environ.copy is not file copy. |
| 83 | env/create | technical_cache, model_download | Configure HOME/XDG/HF/Xet/Torch; mkdir provider cache dirs; os.environ.copy is not file copy. |
| 84 | env/create | technical_cache, model_download | Configure HOME/XDG/HF/Xet/Torch; mkdir provider cache dirs; os.environ.copy is not file copy. |
| 87 | native write/read | model_weights, model_download, technical_cache, service_log | HF hub local_dir may write .cache/huggingface metadata, lock/incomplete; subprocess stdout/stderr into log and error tail. |
| 88 | native write/read | model_weights, model_download, technical_cache, service_log | HF hub local_dir may write .cache/huggingface metadata, lock/incomplete; subprocess stdout/stderr into log and error tail. |
| 97 | native write/read | model_weights, model_download, technical_cache, service_log | HF hub local_dir may write .cache/huggingface metadata, lock/incomplete; subprocess stdout/stderr into log and error tail. |
| 101 | delete/create | model_source, model_download | Existing source target, clear/create private staging. |
| 104 | delete/create | model_source, model_download | Existing source target, clear/create private staging. |
| 105 | delete/create | model_source, model_download | Existing source target, clear/create private staging. |
| 109 | write | model_download | HTTP download ZIP to .part with size bound. |
| 116 | write | model_download | HTTP download ZIP to .part with size bound. |
| 119 | read/extract | model_download | Open ZIP, validated entries, create directories and copy Python/license files; no arbitrary extraction. |
| 133 | read/extract | model_download | Open ZIP, validated entries, create directories and copy Python/license files; no arbitrary extraction. |
| 134 | read/extract | model_download | Open ZIP, validated entries, create directories and copy Python/license files; no arbitrary extraction. |
| 137 | publish/copy | model_source | Rename staging if absent else copy missing files into source tree; not fully atomic replacement. |
| 138 | publish/copy | model_source | Rename staging if absent else copy missing files into source tree; not fully atomic replacement. |
| 140 | publish/copy | model_source | Rename staging if absent else copy missing files into source tree; not fully atomic replacement. |
| 144 | publish/copy | model_source | Rename staging if absent else copy missing files into source tree; not fully atomic replacement. |
| 145 | publish/copy | model_source | Rename staging if absent else copy missing files into source tree; not fully atomic replacement. |
| 147 | delete | model_download | Remove downloaded ZIP and staging in finally. |
| 148 | delete | model_download | Remove downloaded ZIP and staging in finally. |
| 157 | native write/read | service_log, model_source, model_weights, technical_cache | Verification subprocess imports loader and weights; stdout/stderr log, inspect MODEL_OK. |
| 158 | native write/read | service_log, model_source, model_weights, technical_cache | Verification subprocess imports loader and weights; stdout/stderr log, inspect MODEL_OK. |
| 159 | native write/read | service_log, model_source, model_weights, technical_cache | Verification subprocess imports loader and weights; stdout/stderr log, inspect MODEL_OK. |
| 160 | native write/read | service_log, model_source, model_weights, technical_cache | Verification subprocess imports loader and weights; stdout/stderr log, inspect MODEL_OK. |

## `PhotoSorter/backend/app/recognition/engines/megaloc/loader.py`

Zero lexical hits; importlib executes local megaloc_model.py; safetensors.load_file reads weight on CPU, model constructor may call third-party caches; runtime offline flag, source/weight not disposable.

## `PhotoSorter/backend/app/logging/events.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 7 | config/path | run_log | Run path root. |
| 19 | config/path | run_log | Run path root. |
| 29 | rotate/stat/delete | run_log | Rotate oldest segments and aggregate budget scan; verify active segment coordination. |
| 32 | rotate/stat/delete | run_log | Rotate oldest segments and aggregate budget scan; verify active segment coordination. |
| 33 | rotate/stat/delete | run_log | Rotate oldest segments and aggregate budget scan; verify active segment coordination. |
| 37 | rotate/stat/delete | run_log | Rotate oldest segments and aggregate budget scan; verify active segment coordination. |
| 40 | rotate/stat/delete | run_log | Rotate oldest segments and aggregate budget scan; verify active segment coordination. |
| 42 | rotate/stat/delete | run_log | Rotate oldest segments and aggregate budget scan; verify active segment coordination. |
| 44 | rotate/stat/delete | run_log | Rotate oldest segments and aggregate budget scan; verify active segment coordination. |
| 45 | rotate/stat/delete | run_log | Rotate oldest segments and aggregate budget scan; verify active segment coordination. |
| 59 | append | run_log | Create folder, rotate on size, append JSONL. |
| 60 | append | run_log | Create folder, rotate on size, append JSONL. |
| 62 | append | run_log | Create folder, rotate on size, append JSONL. |
| 80 | read/seek | run_log | Read/tail/paginate log segments and validate cursor against file size. |
| 116 | read/seek | run_log | Read/tail/paginate log segments and validate cursor against file size. |
| 118 | read/seek | run_log | Read/tail/paginate log segments and validate cursor against file size. |
| 131 | stat/read | run_log | Usage and newest cursor; no separate log data. |
| 132 | stat/read | run_log | Usage and newest cursor; no separate log data. |
| 141 | stat/read | run_log | Usage and newest cursor; no separate log data. |

## `PhotoSorter/backend/server/services/result_pages.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 6 | config | result_metadata | Root import. |
| 28 | read | result_metadata | JSONL iterator and fallback manifest JSON. |
| 31 | read | result_metadata | JSONL iterator and fallback manifest JSON. |
| 47 | read/seek | result_metadata | Byte offset cursor and size check. |
| 51 | read/seek | result_metadata | Byte offset cursor and size check. |
| 52 | read/seek | result_metadata | Byte offset cursor and size check. |

## `install.sh`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 7 | non-file | installation_state | Usage/check guards and stdout/stderr, no mutations on check. |
| 9 | non-file | installation_state | Usage/check guards and stdout/stderr, no mutations on check. |
| 12 | non-file | installation_state | Usage/check guards and stdout/stderr, no mutations on check. |
| 14 | non-file | installation_state | Usage/check guards and stdout/stderr, no mutations on check. |
| 15 | config read/write | deployment_config | Copy template .env if missing, source .env; secrets outside data root. |
| 20 | config read/write | deployment_config | Copy template .env if missing, source .env; secrets outside data root. |
| 21 | config read/write | deployment_config | Copy template .env if missing, source .env; secrets outside data root. |
| 26 | non-file | system_runtime | Validation/check prerequisites and engine status; no managed write. |
| 30 | non-file | system_runtime | Validation/check prerequisites and engine status; no managed write. |
| 34 | non-file | system_runtime | Validation/check prerequisites and engine status; no managed write. |
| 35 | non-file | system_runtime | Validation/check prerequisites and engine status; no managed write. |
| 37 | non-file | system_runtime | Validation/check prerequisites and engine status; no managed write. |
| 42 | non-file | system_runtime | Validation/check prerequisites and engine status; no managed write. |
| 43 | non-file | system_runtime | Validation/check prerequisites and engine status; no managed write. |
| 51 | engine read/guard | postgres_data, deployment_config | Inspect old named volume and block missing creds; v2 inspect PGDATA. |
| 56 | engine read/guard | postgres_data, deployment_config | Inspect old named volume and block missing creds; v2 inspect PGDATA. |
| 57 | engine read/guard | postgres_data, deployment_config | Inspect old named volume and block missing creds; v2 inspect PGDATA. |
| 60 | engine read/guard | postgres_data, deployment_config | Inspect old named volume and block missing creds; v2 inspect PGDATA. |
| 61 | write/read | deployment_config | umask 077 generate .env.generated, validate completeness. |
| 71 | write/read | deployment_config | umask 077 generate .env.generated, validate completeness. |
| 99 | non-file | system_runtime | Compose command array and CPU validation, no file writes. |
| 111 | non-file | system_runtime | Compose command array and CPU validation, no file writes. |
| 121 | non-file | system_runtime | Compose command array and CPU validation, no file writes. |
| 134 | chmod | deployment_config | Protect .env secrets. |
| 139 | read | host_config | sysctl probe and fallback. |
| 142 | read | host_config | sysctl probe and fallback. |
| 145 | create/chown | installation_state, model_weights, technical_cache, fo_original, reference_gallery, run_state | Create old roots and app UID ownership; chown only old storage, replace with scoped bootstrap. |
| 149 | create/chown | installation_state, model_weights, technical_cache, fo_original, reference_gallery, run_state | Create old roots and app UID ownership; chown only old storage, replace with scoped bootstrap. |
| 151 | create/chown | installation_state, model_weights, technical_cache, fo_original, reference_gallery, run_state | Create old roots and app UID ownership; chown only old storage, replace with scoped bootstrap. |
| 154 | create/chown | installation_state, model_weights, technical_cache, fo_original, reference_gallery, run_state | Create old roots and app UID ownership; chown only old storage, replace with scoped bootstrap. |
| 158 | lock/build | updater_control, runtime_image, build_cache | Root deploy.lock, map_build invokes disposable build from current SHA. |
| 159 | lock/build | updater_control, runtime_image, build_cache | Root deploy.lock, map_build invokes disposable build from current SHA. |
| 161 | lock/build | updater_control, runtime_image, build_cache | Root deploy.lock, map_build invokes disposable build from current SHA. |
| 166 | lock/build | updater_control, runtime_image, build_cache | Root deploy.lock, map_build invokes disposable build from current SHA. |
| 178 | host config/service | host_config, audit_event | Writes systemd observer unit and starts service; remove automatic unbounded observer at stage 6. |
| 181 | host config/service | host_config, audit_event | Writes systemd observer unit and starts service; remove automatic unbounded observer at stage 6. |
| 184 | host config/service | host_config, audit_event | Writes systemd observer unit and starts service; remove automatic unbounded observer at stage 6. |
| 185 | host config/service | host_config, audit_event | Writes systemd observer unit and starts service; remove automatic unbounded observer at stage 6. |
| 205 | host config/service | host_config, audit_event | Writes systemd observer unit and starts service; remove automatic unbounded observer at stage 6. |
| 216 | non-file | audit_snapshot | Warning only; host audit invocation writes reports indirectly. |

## `compose.yaml`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 3 | config | postgres_data | DB URL env, no file. |
| 18 | mount | updater_control | RO control path. |
| 39 | mount | runtime_image | Caddy source config RO. |
| 52 | build | runtime_image, build_cache | App Dockerfile build specification. |
| 61 | mount | updater_control, system_runtime | RO control and RPC socket. |
| 62 | mount | updater_control, system_runtime | RO control and RPC socket. |
| 79 | build | runtime_image, build_cache | Same image builds declared for worker/cleanup/thumbnail; actual deployment builds once. |
| 97 | build | runtime_image, build_cache | Same image builds declared for worker/cleanup/thumbnail; actual deployment builds once. |
| 115 | build | runtime_image, build_cache | Same image builds declared for worker/cleanup/thumbnail; actual deployment builds once. |
| 135 | config/mount | postgres_data, deployment_config | PG credential and volume; native PG writer. |
| 137 | config/mount | postgres_data, deployment_config | PG credential and volume; native PG writer. |

## `PhotoSorter/docker/app/Dockerfile`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 4 | build | runtime_image, build_cache | Npm package install/build and static assets; build layers and npm cache, no persistent application path. |
| 5 | build | runtime_image, build_cache | Npm package install/build and static assets; build layers and npm cache, no persistent application path. |
| 6 | build | runtime_image, build_cache | Npm package install/build and static assets; build layers and npm cache, no persistent application path. |
| 7 | build | runtime_image, build_cache | Npm package install/build and static assets; build layers and npm cache, no persistent application path. |
| 8 | build | runtime_image, build_cache | Npm package install/build and static assets; build layers and npm cache, no persistent application path. |
| 9 | build | runtime_image, build_cache | Npm package install/build and static assets; build layers and npm cache, no persistent application path. |
| 12 | env | technical_cache | Bytecode disabled, HOME/XDG/HF/Xet/Torch cache roots; TMPDIR not set. |
| 14 | env | technical_cache | Bytecode disabled, HOME/XDG/HF/Xet/Torch cache roots; TMPDIR not set. |
| 15 | env | technical_cache | Bytecode disabled, HOME/XDG/HF/Xet/Torch cache roots; TMPDIR not set. |
| 16 | env | technical_cache | Bytecode disabled, HOME/XDG/HF/Xet/Torch cache roots; TMPDIR not set. |
| 18 | build | runtime_image, build_cache | Apt/pip dependency install in image; apt lists removed, pip cache disabled. |
| 20 | build | runtime_image, build_cache | Apt/pip dependency install in image; apt lists removed, pip cache disabled. |
| 21 | build | runtime_image, build_cache | Apt/pip dependency install in image; apt lists removed, pip cache disabled. |
| 22 | build | runtime_image, build_cache | Apt/pip dependency install in image; apt lists removed, pip cache disabled. |
| 23 | build/config | runtime_image | Copy backend/frontend, dist; app UID 10001. Build-context exclusion needed. |
| 24 | build/config | runtime_image | Copy backend/frontend, dist; app UID 10001. Build-context exclusion needed. |
| 25 | build/config | runtime_image | Copy backend/frontend, dist; app UID 10001. Build-context exclusion needed. |
| 26 | build/config | runtime_image | Copy backend/frontend, dist; app UID 10001. Build-context exclusion needed. |
| 27 | build/config | runtime_image | Copy backend/frontend, dist; app UID 10001. Build-context exclusion needed. |

## `PhotoSorter/docker/caddy/Caddyfile`

Zero lexical hits; native Caddy creates TLS/ACME and autosave under /data,/config, runtime logs stderr; no access log configured; preserve HTTP/1.1, body limit and proxy timeouts.

## `PhotoSorter/tools/maintenance/map_updater.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 14 | config | updater_control, updater_workspace | Import and root. |
| 23 | config | updater_control, updater_workspace | Import and root. |
| 43 | native process | system_runtime | Capture subprocess output in memory; command-specific FS effects classified below. |
| 44 | native process | system_runtime | Capture subprocess output in memory; command-specific FS effects classified below. |
| 55 | atomic write | updater_control, atomic_fragment | Status JSON temp, fsync, replace. |
| 58 | atomic write | updater_control, atomic_fragment | Status JSON temp, fsync, replace. |
| 60 | atomic write | updater_control, atomic_fragment | Status JSON temp, fsync, replace. |
| 103 | DB read | postgres_data | Obsolete archive_retries running count blocks updater; remove only after caller check. |
| 131 | stat | system_runtime | Free disk preflight across root/engine paths. |
| 132 | stat | system_runtime | Free disk preflight across root/engine paths. |
| 136 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 138 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 141 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 142 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 143 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 146 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 147 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 148 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 149 | backup write/read | updater_backup, deployment_config | Private dir, copy config, pg_dump stdout to file, fsync and pg_restore -l validation. |
| 169 | read | updater_control | Exception handling and status JSON recovery. |
| 179 | read | updater_control | Exception handling and status JSON recovery. |
| 257 | lock | updater_control | Stable root deploy.lock exclusive. |
| 258 | lock | updater_control | Stable root deploy.lock exclusive. |
| 271 | inspect/stat | updater_control, system_runtime | Check bind mount/control lock visibility, sample disk. |
| 274 | inspect/stat | updater_control, system_runtime | Check bind mount/control lock visibility, sample disk. |
| 276 | inspect/stat | updater_control, system_runtime | Check bind mount/control lock visibility, sample disk. |
| 279 | workspace write/delete | updater_workspace | Temporary private source dir, git archive writes tar, tar extraction, remove tar; builder consumes source. |
| 281 | workspace write/delete | updater_workspace | Temporary private source dir, git archive writes tar, tar extraction, remove tar; builder consumes source. |
| 282 | workspace write/delete | updater_workspace | Temporary private source dir, git archive writes tar, tar extraction, remove tar; builder consumes source. |
| 284 | workspace write/delete | updater_workspace | Temporary private source dir, git archive writes tar, tar extraction, remove tar; builder consumes source. |
| 285 | workspace write/delete | updater_workspace | Temporary private source dir, git archive writes tar, tar extraction, remove tar; builder consumes source. |
| 289 | marker/lock | updater_control | Durable marker create then exclusive gate lock. |
| 291 | marker/lock | updater_control | Durable marker create then exclusive gate lock. |
| 295 | marker/lock | updater_control | Durable marker create then exclusive gate lock. |
| 331 | delete | updater_backup | Error handling; prune only own prior backup dirs after success. |
| 339 | delete | updater_backup | Error handling; prune only own prior backup dirs after success. |
| 341 | delete | updater_backup | Error handling; prune only own prior backup dirs after success. |
| 344 | stat/delete | updater_control | Free-space result and maintenance marker remove on safe completion/recovery. |
| 345 | stat/delete | updater_control | Free-space result and maintenance marker remove on safe completion/recovery. |
| 359 | stat/delete | updater_control | Free-space result and maintenance marker remove on safe completion/recovery. |
| 380 | socket write | system_runtime | wfile sends RPC response, not disk. |
| 392 | stat/delete | system_runtime | Check root ownership/mode, unlink stale socket before bind. |
| 395 | stat/delete | system_runtime | Check root ownership/mode, unlink stale socket before bind. |
| 404 | delete | system_runtime | Unlink RPC socket on shutdown. |

## `PhotoSorter/tools/maintenance/map_build.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 4 | native process | runtime_image, build_cache | Wrapper subprocess invokes Docker buildx, engine manages writes. |
| 8 | native process | runtime_image, build_cache | Wrapper subprocess invokes Docker buildx, engine manages writes. |
| 13 | native process | runtime_image, build_cache | Wrapper subprocess invokes Docker buildx, engine manages writes. |
| 16 | create/delete | builder_marker | Create private marker root, remove marker only after owned builder cleanup. |
| 23 | create/delete | builder_marker | Create private marker root, remove marker only after owned builder cleanup. |
| 24 | non-file | builder_marker | Exception type. |
| 34 | create/delete | builder_marker, build_cache | Exclusive marker per own builder, remove after lifecycle. |
| 44 | create/delete | builder_marker, build_cache | Exclusive marker per own builder, remove after lifecycle. |
| 45 | non-file | build_cache | Exception handling. |

## `PhotoSorter/tools/maintenance/install_map_updater.sh`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 6 | create/permission | updater_control, updater_workspace, system_runtime, host_config | Root-only dirs, stable lock touch/chown/chmod. |
| 7 | create/permission | updater_control, updater_workspace, system_runtime, host_config | Root-only dirs, stable lock touch/chown/chmod. |
| 9 | create/permission | updater_control, updater_workspace, system_runtime, host_config | Root-only dirs, stable lock touch/chown/chmod. |
| 10 | create/permission | updater_control, updater_workspace, system_runtime, host_config | Root-only dirs, stable lock touch/chown/chmod. |
| 11 | create/permission | updater_control, updater_workspace, system_runtime, host_config | Root-only dirs, stable lock touch/chown/chmod. |
| 12 | install/write | host_config | Install root executable Python and write systemd unit. |
| 13 | install/write | host_config | Install root executable Python and write systemd unit. |
| 14 | install/write | host_config | Install root executable Python and write systemd unit. |
| 17 | service config | host_config | Systemd dependencies and ExecStart, no app access. |
| 18 | service config | host_config | Systemd dependencies and ExecStart, no app access. |
| 26 | service config | host_config | Systemd dependencies and ExecStart, no app access. |

## `PhotoSorter/tools/maintenance/snapshot.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 16 | non-file | external_backup | Import. |
| 29 | read | external_backup | SHA256 file read. |
| 37 | native process | external_backup, postgres_data | Env copy and pg_dump/restore wrapper; stdout capture, not itself path. |
| 53 | native process | external_backup, postgres_data | Env copy and pg_dump/restore wrapper; stdout capture, not itself path. |
| 54 | native process | external_backup, postgres_data | Env copy and pg_dump/restore wrapper; stdout capture, not itself path. |
| 85 | scan | external_backup | Enumerate selected source roots. |
| 106 | write/read/stat | external_backup | Tar capture, preserve inode/hardlinks, verify source stamps. |
| 110 | write/read/stat | external_backup | Tar capture, preserve inode/hardlinks, verify source stamps. |
| 135 | write/read/stat | external_backup | Tar capture, preserve inode/hardlinks, verify source stamps. |
| 141 | write/read/stat | external_backup | Tar capture, preserve inode/hardlinks, verify source stamps. |
| 155 | stage/publish/delete | external_backup | Explicit destination parent, mkdtemp sibling, manifest write, rename and failed scratch rmtree. |
| 156 | stage/publish/delete | external_backup | Explicit destination parent, mkdtemp sibling, manifest write, rename and failed scratch rmtree. |
| 169 | stage/publish/delete | external_backup | Explicit destination parent, mkdtemp sibling, manifest write, rename and failed scratch rmtree. |
| 172 | stage/publish/delete | external_backup | Explicit destination parent, mkdtemp sibling, manifest write, rename and failed scratch rmtree. |
| 175 | stage/publish/delete | external_backup | Explicit destination parent, mkdtemp sibling, manifest write, rename and failed scratch rmtree. |
| 180 | read | external_backup | Manifest and tar verify. |
| 189 | read | external_backup | Manifest and tar verify. |
| 231 | read | external_backup | Manifest and staging-only marker guard. |
| 239 | read | external_backup | Manifest and staging-only marker guard. |
| 246 | restore | external_backup | Fresh protected target dir, exclusive files, hardlinks/symlinks only validated members; never active project. |
| 248 | restore | external_backup | Fresh protected target dir, exclusive files, hardlinks/symlinks only validated members; never active project. |
| 250 | restore | external_backup | Fresh protected target dir, exclusive files, hardlinks/symlinks only validated members; never active project. |
| 254 | restore | external_backup | Fresh protected target dir, exclusive files, hardlinks/symlinks only validated members; never active project. |
| 256 | restore | external_backup | Fresh protected target dir, exclusive files, hardlinks/symlinks only validated members; never active project. |
| 257 | restore | external_backup | Fresh protected target dir, exclusive files, hardlinks/symlinks only validated members; never active project. |
| 263 | restore | external_backup | Fresh protected target dir, exclusive files, hardlinks/symlinks only validated members; never active project. |
| 266 | restore | external_backup | Fresh protected target dir, exclusive files, hardlinks/symlinks only validated members; never active project. |

## `PhotoSorter/tools/maintenance/audit_host.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 17 | native read | system_runtime | Docker CLI metadata; default shared dirs not exclusive MAP. |
| 28 | native read | system_runtime | Docker CLI metadata; default shared dirs not exclusive MAP. |
| 38 | native read | system_runtime | Docker CLI metadata; default shared dirs not exclusive MAP. |
| 39 | native read | system_runtime | Docker CLI metadata; default shared dirs not exclusive MAP. |
| 59 | read/config | system_runtime | Read device/name evidence and containerd root. |
| 90 | read/config | system_runtime | Read device/name evidence and containerd root. |
| 247 | scan/read | audit_snapshot | lstat, walk, dpkg-query package ownership; no file content reads of user media. |
| 281 | scan/read | audit_snapshot | lstat, walk, dpkg-query package ownership; no file content reads of user media. |
| 299 | scan/read | audit_snapshot | lstat, walk, dpkg-query package ownership; no file content reads of user media. |
| 335 | scan/read | audit_snapshot | lstat, walk, dpkg-query package ownership; no file content reads of user media. |
| 343 | scan/read | audit_snapshot | lstat, walk, dpkg-query package ownership; no file content reads of user media. |
| 359 | read/stat | system_runtime | Read cgroup and deleted-open fd metadata. |
| 374 | read/stat | system_runtime | Read cgroup and deleted-open fd metadata. |
| 386 | create | audit_snapshot, atomic_fragment | Report dir and temp CSV. |
| 394 | create | audit_snapshot, atomic_fragment | Report dir and temp CSV. |
| 398 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 400 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 405 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 408 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 409 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 411 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 416 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 420 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 428 | scan | audit_snapshot | Project/engine/external images/updater/shared/tmp views; read metadata, dedup/coverage. |
| 439 | write/delete | audit_snapshot, atomic_fragment | Temporary source write-sites CSV, remove failed temp. |
| 444 | write/delete | audit_snapshot, atomic_fragment | Temporary source write-sites CSV, remove failed temp. |
| 445 | write/delete | audit_snapshot, atomic_fragment | Temporary source write-sites CSV, remove failed temp. |
| 491 | publish | audit_snapshot, atomic_fragment | Temp JSON and atomic replace three latest reports. |
| 494 | publish | audit_snapshot, atomic_fragment | Temp JSON and atomic replace three latest reports. |
| 497 | publish | audit_snapshot, atomic_fragment | Temp JSON and atomic replace three latest reports. |
| 500 | publish | audit_snapshot, atomic_fragment | Temp JSON and atomic replace three latest reports. |
| 501 | publish | audit_snapshot, atomic_fragment | Temp JSON and atomic replace three latest reports. |
| 505 | delete | atomic_fragment | Finally remove remaining report temp. |
| 506 | delete | atomic_fragment | Finally remove remaining report temp. |

## `PhotoSorter/tools/maintenance/audit_live.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 21 | native read | system_runtime | Import and docker inspect subprocess, metadata only. |
| 56 | native read | system_runtime | Import and docker inspect subprocess, metadata only. |
| 71 | read/path | system_runtime | mountinfo, host roots and category label, no write. |
| 90 | read/path | system_runtime | mountinfo, host roots and category label, no write. |
| 115 | read/path | system_runtime | mountinfo, host roots and category label, no write. |
| 137 | create/append | audit_event | Report mkdir/permissions, opens live-events.jsonl append; current unbounded. |
| 139 | create/append | audit_event | Report mkdir/permissions, opens live-events.jsonl append; current unbounded. |
| 145 | create/append | audit_event | Report mkdir/permissions, opens live-events.jsonl append; current unbounded. |
| 149 | create/append | audit_event | Report mkdir/permissions, opens live-events.jsonl append; current unbounded. |
| 159 | write | audit_event | Per-event JSONL append; replace with bounded opt-in. |
| 234 | scan/read | audit_event | Watch discovery scandir/stat and exception handling; no media writes. |
| 257 | scan/read | audit_event | Watch discovery scandir/stat and exception handling; no media writes. |
| 320 | scan/read | audit_event | Watch discovery scandir/stat and exception handling; no media writes. |
| 363 | non-file | audit_event | Coverage disclaimer string. |
| 368 | publish | audit_snapshot, atomic_fragment | Write temp live-state then replace. |
| 370 | publish | audit_snapshot, atomic_fragment | Write temp live-state then replace. |

## `PhotoSorter/tools/maintenance/audit_containerd.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 14 | non-file | system_runtime | Import. |
| 38 | non-file | system_runtime | String unescape via replace, not filesystem rename. |
| 41 | non-file | system_runtime | String unescape via replace, not filesystem rename. |
| 84 | native read | system_runtime | ctr metadata commands and executable lookup; no deletion. |
| 86 | native read | system_runtime | ctr metadata commands and executable lookup; no deletion. |
| 103 | native read | system_runtime | ctr metadata commands and executable lookup; no deletion. |
| 117 | read | system_runtime | Proc mountinfo read, exception handling. |
| 168 | read | system_runtime | Proc mountinfo read, exception handling. |

## `PhotoSorter/tools/maintenance/ci_restore_drill.py`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 33 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 38 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 39 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 40 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 41 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 42 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 43 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 45 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 46 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 50 | test fixture | test_artifact | Disposable directory, synthetic files/config, hardlink, marker; not production. |
| 55 | test read | test_artifact | Assert content and inode equality after restore. |
| 56 | test read | test_artifact | Assert content and inode equality after restore. |

## `PhotoSorter/tools/maintenance/smoke_container.sh`

| Base line | Effect | Target categories | Semantic role and migration constraint |
|---:|---|---|---|
| 6 | non-file | test_artifact | CI-only guard. |
| 21 | test create/chown | test_artifact | Synthetic current layout roots. |
| 22 | test create/chown | test_artifact | Synthetic current layout roots. |
| 25 | test engine | test_artifact | Compose ps/logs/down on ephemeral runner. |
| 26 | test engine | test_artifact | Compose ps/logs/down on ephemeral runner. |
| 27 | test engine | test_artifact | Compose ps/logs/down on ephemeral runner. |
| 31 | test engine/control | test_artifact | Create test lock/build marker dir, build, inspect, start disposable services. |
| 32 | test engine/control | test_artifact | Create test lock/build marker dir, build, inspect, start disposable services. |
| 33 | test engine/control | test_artifact | Create test lock/build marker dir, build, inspect, start disposable services. |
| 34 | test engine/control | test_artifact | Create test lock/build marker dir, build, inspect, start disposable services. |
| 35 | test engine/control | test_artifact | Create test lock/build marker dir, build, inspect, start disposable services. |
| 36 | test engine/control | test_artifact | Create test lock/build marker dir, build, inspect, start disposable services. |
| 37 | test engine/control | test_artifact | Create test lock/build marker dir, build, inspect, start disposable services. |
| 41 | test read | test_artifact | HTTPS health and static routes. |
| 45 | test read | test_artifact | HTTPS health and static routes. |
| 48 | test read | test_artifact | HTTPS health and static routes. |
| 49 | test read | test_artifact | HTTPS health and static routes. |
| 53 | test credential | test_artifact | Temporary 0600 cookie, trap cleanup; login only synthetic credentials. |
| 54 | test credential | test_artifact | Temporary 0600 cookie, trap cleanup; login only synthetic credentials. |
| 55 | test credential | test_artifact | Temporary 0600 cookie, trap cleanup; login only synthetic credentials. |
| 59 | test credential | test_artifact | Temporary 0600 cookie, trap cleanup; login only synthetic credentials. |
| 63 | test read | test_artifact | Heartbeat JSON check and failure message. |
| 69 | test read | test_artifact | Heartbeat JSON check and failure message. |
| 74 | test marker | test_artifact | Create/remove maintenance marker on disposable host. |
| 76 | test marker | test_artifact | Create/remove maintenance marker on disposable host. |
| 77 | test marker | test_artifact | Create/remove maintenance marker on disposable host. |
| 82 | test API | test_artifact | Read test batch then delete via API. |
| 83 | test API | test_artifact | Read test batch then delete via API. |
| 85 | test API | test_artifact | Read test batch then delete via API. |
