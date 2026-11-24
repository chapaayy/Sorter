# Baseline source-site candidates — references, archives, models, logs

Pinned SHA: c6d77ebb1c9c80c732df209a17a993dd38ec381f. Lexical index, not semantic review or complete coverage. Includes false positives and may miss aliases, indirect calls and native writes. No runtime data accessed.

## `PhotoSorter/backend/server/services/reference_imports.py`

Blob `007d9b6039b17907efe6fc428bc4b6136c8cd3fe`; 274 lines.

- L121: `storage.verify(row["target_path"],storage.ROOT,key[2],digest=key[1])`

## `PhotoSorter/backend/server/services/reference_uploads.py`

Blob `ad65ce68c069e06605098818f0f8ae8bcac5502b`; 134 lines.

- L26: `storage.verify(match["target_path"],storage.ROOT,`
- L83: `with part.open("rb") as stream:`

## `PhotoSorter/backend/server/services/reference_publication.py`

Blob `d556946eeae5544e22edf9157cf56f1bdefa5d42`; 103 lines.

- L15: `def digest_members(members,model_signature):`
- L18: `return hashlib.sha256(json.dumps([model_signature,content],`
- L24: `reference_objects.verify(member["target_path"],reference_objects.ROOT,`
- L31: `SELECT current_version_id FROM reference_library_state WHERE id=1 FOR UPDATE`
- L35: `if state["current_version_id"] is not None:`
- L37: `SELECT 1 FROM reference_version_members`
- L39: `""",(state["current_version_id"],)).fetchone()`
- L47: `INSERT INTO reference_library_versions(version_number,manifest_digest,model_signature)`
- L51: `SET current_version_id=%s,baseline_state='ready',`
- L59: `def publish(db,members,model_signature,*,job_id=None,event_kind="reference_prepared"):`
- L66: `digest=digest_members(members,model_signature)`
- L74: `model_signature,preparation_job_id)`
- L76: `""",(number,digest,model_signature,job_id)).fetchone()["id"]`
- L80: `INSERT INTO reference_version_members(version_id,reference_id,`
- L81: `sam,filename,source_hash,target_path,declared_size,source_kind)`
- L84: `m["target_path"],m["declared_size"]) for m in members])`
- L86: `SET current_version_id=%s,baseline_state='ready',`
- L100: `return [{"path":m["target_path"],"sam":m["sam"],"hash":m["source_hash"],`

## `PhotoSorter/backend/server/services/reference_gallery.py`

Blob `6b0a7b3365fccdf4f57b81434322a641c0b6b74b`; 41 lines.

- L9: `from app.config import DATA_DIR`
- L14: `GALLERY=DATA_DIR/"references"`
- L20: `target_dir.mkdir(parents=True,exist_ok=True)`
- L27: `os.link(source,target,follow_symlinks=False)`
- L36: `received,checksum,finalized,target_path)`

## `PhotoSorter/backend/server/db/repositories/reference_versions.py`

Blob `5b1142da27df235c6a76100cf74adbfff84d27c6`; 18 lines.

- L7: `v.manifest_digest,v.model_signature,v.published_at`
- L9: `LEFT JOIN reference_library_versions v ON v.id=s.current_version_id`
- L15: `SELECT reference_id,sam,filename,source_hash,target_path,declared_size,source_kind`
- L16: `FROM reference_version_members WHERE version_id=%s ORDER BY sam,reference_id`

## `PhotoSorter/backend/server/services/thumbnail_gc.py`

Blob `aa8a7fe3ebb01a014946f89d0aecb0287b63d181`; 6 lines.



## `PhotoSorter/backend/server/services/thumbnails.py`

Blob `57f4909ab8209e0d4a2596e8df5f8401143357ab`; 185 lines.

- L13: `from app.config import DATA_DIR`
- L31: `row=db.execute("""SELECT t.upload_id,t.checksum,t.version,u.kind,u.batch_id,u.sam,u.target_path,`
- L46: `root=(DATA_DIR/"uploads"/str(task["batch_id"])) if task["kind"]=="fo" else (`
- L47: `DATA_DIR/"references"/str(task["sam"]))`
- L48: `path=owned_file(Path(task["target_path"]),root)`
- L57: `destination.parent.mkdir(parents=True,exist_ok=True)`
- L58: `fd,name=tempfile.mkstemp(prefix=".thumb-",suffix=".webp.tmp",dir=destination.parent)`
- L61: `with Image.open(source) as img:`
- L62: `img.load()`
- L86: `img.save(output,format="WEBP",quality=cache.QUALITY,method=4)`
- L88: `os.fsync(output.fileno())`
- L90: `os.replace(tmp,destination)`
- L93: `tmp.unlink(missing_ok=True)`
- L105: `with tempfile.TemporaryDirectory() as tmp:`
- L154: `for path in root.glob(f"v{cache.VERSION}/*/*.webp"):`
- L158: `if time.time()-path.stat().st_mtime<grace_seconds:continue`
- L166: `path.unlink(missing_ok=True)`
- L175: `for path in cache.ROOT.glob(f"v{cache.VERSION}/*/.thumb-*.webp.tmp"):`
- L180: `if time.time()-path.stat().st_mtime<grace_seconds:continue`
- L181: `path.unlink(missing_ok=True)`

## `PhotoSorter/backend/server/services/reference_archives.py`

Blob `283c10fdd6a07362cee4e46dbbc44aee8ad6cb3e`; 144 lines.

- L21: `from app.config import DATA_DIR`
- L30: `EXPORTS = DATA_DIR / "reference_exports"`
- L52: `source = Path(item["target_path"])`
- L99: `EXPORTS.mkdir(parents=True, exist_ok=True)`
- L105: `with archive_cache.pin(directory), os.fdopen(os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "a+b") as handle:`
- L106: `fcntl.flock(handle.fileno(), fcntl.LOCK_EX)`
- L112: `target.unlink()`
- L121: `fcntl.flock(handle.fileno(), fcntl.LOCK_UN)`
- L125: `fd, temporary = tempfile.mkstemp(prefix=".references-", suffix=".tmp", dir=directory)`
- L128: `with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED,`
- L132: `archive.write(source, arcname=name, compress_type=zipfile.ZIP_STORED)`
- L134: `os.fsync(output.fileno())`
- L135: `with zipfile.ZipFile(temporary) as archive:`
- L140: `os.replace(temporary, target)`
- L143: `Path(temporary).unlink(missing_ok=True)`

## `PhotoSorter/backend/server/services/temp_cleanup.py`

Blob `c45238a2070f9ddffa468ca60613689cad80cbf1`; 38 lines.

- L4: `from app.config import DATA_DIR`
- L8: `PARTS=DATA_DIR/"incoming"`
- L32: `if target.exists() and time.time()-target.stat().st_mtime<AGE_DAYS*86400:continue`
- L33: `target.unlink(missing_ok=True)`

## `PhotoSorter/backend/server/workers/cleanup.py`

Blob `391f9991ee72112db0216c06ab59bb30b5d48221`; 71 lines.



## `PhotoSorter/backend/app/system/model_store.py`

Blob `6f8ba2fa79ccf814881884dde13219baae7ded7b`; 109 lines.

- L12: `from ..config import MODELS_DIR, WEIGHTS_DIR, MODEL_CACHE_DIR, DATA_DIR`
- L18: `VERIFICATIONS = MODEL_CACHE_DIR / 'downloads' / 'verified_megaloc.json'`
- L19: `LEGACY_VERIFICATIONS = MODEL_CACHE_DIR / 'downloads' / 'verified_hub.json'`
- L25: `key = os.path.normcase(os.path.abspath(value))`
- L31: `roots = [MODEL_CACHE_DIR / 'torch' / 'hub', DATA_DIR / 'torch' / 'hub']`
- L43: `roots += [MODEL_CACHE_DIR / 'huggingface' / 'hub', Path.home() / '.cache' / 'huggingface' / 'hub']`
- L47: `(MODEL_CACHE_DIR / 'torch' / 'hub').mkdir(parents=True,exist_ok=True)`
- L48: `(MODEL_CACHE_DIR / 'huggingface' / 'hub').mkdir(parents=True,exist_ok=True)`
- L49: `os.environ.setdefault('TORCH_HOME', str(MODEL_CACHE_DIR / 'torch'))`
- L50: `os.environ.setdefault('HF_HUB_CACHE', str(MODEL_CACHE_DIR / 'huggingface' / 'hub'))`
- L59: `return MODEL_CACHE_DIR / 'torch' / 'hub' / SOURCE_FOLDER`
- L63: `candidates = [WEIGHTS_DIR / 'megaloc' / WEIGHT_NAME, MODELS_DIR / 'megaloc' / WEIGHT_NAME]`
- L66: `if candidate.is_file() and candidate.stat().st_size >= MINIMUM_SIZE:`
- L73: `if candidate.is_file() and candidate.stat().st_size >= MINIMUM_SIZE:`
- L85: `stat = weight.stat()`
- L87: `for source in sorted(repo.rglob('*.py')):`
- L89: `hasher.update(source.read_bytes())`
- L97: `data = json.loads(location.read_text('utf8'))`
- L105: `VERIFICATIONS.parent.mkdir(parents=True,exist_ok=True)`
- L107: `tmp.write_text(json.dumps({'megaloc':sig},indent=2),encoding='utf8')`
- L108: `tmp.replace(VERIFICATIONS)`

## `PhotoSorter/backend/app/system/downloads.py`

Blob `978434f0dfdd44af87d2f9754df418c139173c0b`; 163 lines.

- L5: `import subprocess`
- L12: `from ..config import WEIGHTS_DIR, MODEL_CACHE_DIR`
- L15: `LOG_DIR = MODEL_CACHE_DIR / 'downloads'`
- L19: `for root,_,names in os.walk(path):`
- L21: `try: total += (Path(root)/name).stat().st_size`
- L51: `LOG_DIR.mkdir(parents=True,exist_ok=True)`
- L66: `target=WEIGHTS_DIR/'megaloc'`
- L67: `target.mkdir(parents=True,exist_ok=True)`
- L73: `cache=MODEL_CACHE_DIR`
- L83: `folder.mkdir(parents=True,exist_ok=True)`
- L84: `env=os.environ.copy()`
- L87: `with log.open('w',encoding='utf8') as output:`
- L88: `process=subprocess.Popen(cmd,env=env,stdout=output,stderr=subprocess.STDOUT)`
- L97: `if code:raise RuntimeError('Ошибка загрузки весов: '+log.read_text('utf8',errors='replace')[-1200:])`
- L101: `target=MODEL_CACHE_DIR/'torch'/'hub'/model_store.SOURCE_FOLDER`
- L104: `if stage.exists():shutil.rmtree(stage)`
- L105: `stage.mkdir(parents=True)`
- L109: `with urllib.request.urlopen(request,timeout=45) as response, temp.open('wb') as file:`
- L116: `file.write(chunk)`
- L119: `with zipfile.ZipFile(temp) as archive:`
- L133: `destination.parent.mkdir(parents=True,exist_ok=True)`
- L134: `with archive.open(entry) as src, destination.open('wb') as dst:shutil.copyfileobj(src,dst)`
- L137: `target.parent.mkdir(parents=True,exist_ok=True)`
- L138: `if not target.exists():stage.rename(target)`
- L140: `for file in stage.rglob('*'):`
- L144: `dst.parent.mkdir(parents=True,exist_ok=True)`
- L145: `shutil.copy2(file,dst)`
- L147: `temp.unlink(missing_ok=True)`
- L148: `if stage.exists():shutil.rmtree(stage)`
- L157: `with log.open('w',encoding='utf8') as output:`
- L158: `result=subprocess.run([sys.executable,'-c',source,str(backend)],stdout=output,stderr=subprocess.STDOUT,timeout=420)`
- L159: `if result.returncode or 'MODEL_OK' not in log.read_text('utf8',errors='replace'):`
- L160: `raise RuntimeError('Веса найдены, но MegaLoc не загрузилась: '+log.read_text('utf8',errors='replace')[-1300:])`

## `PhotoSorter/backend/app/recognition/engines/megaloc/loader.py`

Blob `d74490fc6d12627c52c97299a81e900d8ab98c6e`; 23 lines.



## `PhotoSorter/backend/app/logging/events.py`

Blob `3b9dea5970f586093d1391a5c8c5725b9174c13b`; 142 lines.

- L7: `from ..config import RUNS_DIR`
- L19: `return RUNS_DIR/str(run_id)`
- L29: `oldest.unlink(missing_ok=True)`
- L32: `if prev.exists():prev.replace(active.with_name(f"{active.name}.{i+1}"))`
- L33: `if active.exists():active.replace(active.with_name(f"{active.name}.1"))`
- L37: `files=[f for f in RUNS_DIR.glob("*/events.jsonl*")`
- L40: `usage=sum(f.stat().st_size for f in files)`
- L42: `for item in sorted(files,key=lambda f:f.stat().st_mtime_ns):`
- L44: `size=item.stat().st_size`
- L45: `item.unlink(missing_ok=True)`
- L59: `path.parent.mkdir(parents=True,exist_ok=True)`
- L60: `if path.exists() and path.stat().st_size+len(payload)>SEGMENT_BYTES:`
- L62: `with path.open("ab") as stream:stream.write(payload)`
- L80: `with f.open("rb") as stream:`
- L116: `with f.open("rb") as stream:`
- L118: `if position[1]>f.stat().st_size:raise ValueError("Stale log cursor")`
- L131: `files=[f for f in RUNS_DIR.glob("*/events.jsonl*") if f.is_file() and not f.is_symlink()]`
- L132: `return {"bytes":sum(f.stat().st_size for f in files),`
- L141: `return {"events":rows,"next_cursor":_encode(newest.name,newest.stat().st_size)}`

## `PhotoSorter/backend/server/services/result_pages.py`

Blob `5d3608cdc2aaaef215d751da5a7d3dfd14c7dba5`; 87 lines.

- L6: `from app.config import DATA_DIR`
- L28: `file=DATA_DIR/"outputs"/run_id/"megaloc"/"manifest.rows.jsonl"`
- L31: `with file.open('r',encoding='utf-8') as stream:`
- L47: `file=DATA_DIR/"outputs"/run_id/"megaloc"/"manifest.rows.jsonl"`
- L51: `with file.open('rb') as stream:`
- L52: `stream.seek(_parse(cursor,selector,file.stat().st_size))`

Failed fetches: none
