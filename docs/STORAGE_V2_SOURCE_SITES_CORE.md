# Baseline source-site candidates — core group

Pinned SHA: c6d77ebb1c9c80c732df209a17a993dd38ec381f. Lexical candidate index of selected core modules, not semantic review or complete coverage. Includes readers, writers, deletions, SQL/path field references; false positives and missed aliases/multiline/native calls possible. Extend by reviewing each module and its callers. No runtime data accessed.

## `PhotoSorter/backend/server/uploads.py`

Blob `00c236ed4de02d11579106818a2680db0efa52bb`; 372 lines.

- L3: `import subprocess`
- L18: `from app.config import DATA_DIR`
- L22: `UPLOADS_DIR=DATA_DIR/'uploads'`
- L23: `PART_DIR=DATA_DIR/'incoming'`
- L78: `PART_DIR.mkdir(parents=True,exist_ok=True)`
- L79: `(PART_DIR/f'{file_id}.part').touch(exist_ok=False)`
- L105: `PART_DIR.mkdir(parents=True,exist_ok=True)`
- L106: `part.touch(exist_ok=True)`
- L107: `offset=part.stat().st_size if part.is_file() else row['received']`
- L125: `offset=part.stat().st_size if part.is_file() else row['received']`
- L132: `with path.open('r+b') as output:`
- L140: `output.write(data)`
- L143: `output.truncate(actual)`
- L200: `return {'path':row['target_path'],'already_finalized':True}`
- L202: `if not part.is_file() or part.stat().st_size!=row['declared_size']:`
- L205: `return {'path':current['target_path'],'already_finalized':True}`
- L207: `with part.open('rb') as stream:`
- L221: `except (OSError,ValueError,subprocess.SubprocessError):`
- L232: `current=db.execute("""SELECT finalized,target_path FROM uploads`
- L235: `return {'path':current['target_path'],'already_finalized':True}`
- L237: `base.mkdir(parents=True,exist_ok=True)`
- L244: `with target.open('rb') as stream:`
- L249: `os.link(part,target)`
- L252: `checksum=%s,target_path=%s,original_media_type=%s,media_action=%s,`
- L262: `part.unlink(missing_ok=True)`
- L321: `return {'already_finalized':True,'path':row['target_path']}`
- L360: `def remove():`
- L365: `(PART_DIR/f"{row['id']}.part").unlink(missing_ok=True)`

## `PhotoSorter/backend/server/database.py`

Blob `35b570988a5a0fa519361f9ed9cee87a1c07fabe`; 112 lines.

- L14: `CREATE TABLE IF NOT EXISTS users (`
- L21: `CREATE TABLE IF NOT EXISTS sessions (`
- L26: `CREATE TABLE IF NOT EXISTS batches (`
- L30: `CREATE TABLE IF NOT EXISTS uploads (`
- L40: `target_path TEXT,`
- L44: `CREATE TABLE IF NOT EXISTS jobs (`
- L54: `CREATE TABLE IF NOT EXISTS reference_cache (`
- L57: `cache_path TEXT NOT NULL,`

## `PhotoSorter/backend/server/jobs.py`

Blob `b7f3729b733fac23bac967ca33a6275cebddd7f9`; 196 lines.

- L8: `from app.config import DATA_DIR`
- L117: `info={"id":run_id,"status":"queued","new_photos":str(DATA_DIR/"uploads"/str(data.batch_id)),`
- L118: `"output":str(DATA_DIR/"outputs"),"batch_id":str(data.batch_id),`
- L184: `def save(self):`
- L185: `super().save()`

## `PhotoSorter/backend/server/services/batches.py`

Blob `35eb196180c26a9f6fb365a8729d4ad44bc2ccb1`; 224 lines.

- L10: `from app.config import DATA_DIR`
- L146: `base=DATA_DIR/"incoming"`
- L151: `actual=part.stat().st_size if exists else 0`
- L159: `with part.open("rb") as stream:`
- L176: `def rename(batch_id,name):`
- L208: `if item["target_path"]:`
- L209: `path=owned_file(item["target_path"],batch_dir(batch_id))`
- L210: `if not repository.path_is_shared(db,item["target_path"],photo_id):`
- L211: `path.unlink(missing_ok=True)`
- L213: `path=owned_file(DATA_DIR/"incoming"/f"{photo_id}.part",DATA_DIR/"incoming")`
- L214: `path.unlink(missing_ok=True)`
- L216: `owned_file(item["media_output_path"],batch_dir(batch_id)).unlink(missing_ok=True)`

## `PhotoSorter/backend/server/storage/batch_cleanup.py`

Blob `e3833b7cb679070d4ab54de8600289537814063b`; 57 lines.

- L8: `from .paths import batch_dir,owned_directory,owned_file,run_dir`
- L13: `trees=[owned_directory(run_dir(run_id,root),root) for run_id in run_ids`
- L21: `fd=os.open(originals,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)`
- L31: `shutil.rmtree(path)`
- L35: `path.unlink(missing_ok=True)`
- L41: `info=os.stat(name,dir_fd=fd,follow_symlinks=False)`
- L43: `shutil.rmtree(name,dir_fd=fd)`
- L45: `os.unlink(name,dir_fd=fd)`
- L50: `originals.rmdir()`

## `PhotoSorter/backend/server/storage/reference_objects.py`

Blob `2d89fa4046eab6d32135dd2abda92283f49c1b33`; 144 lines.

- L15: `from app.config import DATA_DIR`
- L18: `ROOT = DATA_DIR / "reference_staging"`
- L19: `LEGACY_ROOT = DATA_DIR / "references"`
- L42: `if not path.is_file() or path.stat().st_size!=size:`
- L47: `with path.open("rb") as stream:`
- L65: `path.mkdir(parents=True,exist_ok=True)`
- L76: `with target.open("xb"):`
- L88: `length=path.stat().st_size`
- L97: `with path.open("r+b") as stream:`
- L103: `stream.write(data)`
- L105: `os.fsync(stream.fileno())`
- L110: `with Image.open(path) as picture:`
- L130: `os.link(source,target,follow_symlinks=False)`
- L143: `path.unlink(missing_ok=True)`

## `PhotoSorter/backend/server/storage/thumbnail_cache.py`

Blob `767b8d89672abe4c448b162ad77e3d671a02cdbc`; 24 lines.

- L5: `from app.config import DATA_DIR`
- L11: `ROOT=DATA_DIR/"cache"/"thumbnails"`

## `PhotoSorter/backend/server/reference_cache.py`

Blob `31e72e08d89d82263a2286e1ba3da7a8327a3c3e`; 96 lines.

- L12: `from app.config import DATA_DIR`
- L16: `REFERENCE_ROOT=(DATA_DIR/'reference_staging').resolve()`
- L17: `CACHE_DIR=DATA_DIR/'cache'/'megaloc'/'references'`
- L21: `row=db.execute("""SELECT cache_path FROM reference_cache`
- L24: `target=Path(row["cache_path"])`
- L28: `arr=np.load(target,allow_pickle=False)`
- L29: `if arr.ndim==1 and arr.size>0 and np.isfinite(arr).all():`
- L46: `CACHE_DIR.mkdir(parents=True,exist_ok=True)`
- L63: `with path.open('rb') as stream:`
- L83: `with tmp.open('wb') as stream:np.save(stream,np.asarray(vector,dtype='float32'),allow_pickle=False)`
- L84: `tmp.replace(cache)`
- L86: `db.execute('INSERT INTO reference_cache(source_hash,model_signature,cache_path) '`
- L88: `'DO UPDATE SET cache_path=excluded.cache_path',`
- L90: `finally:tmp.unlink(missing_ok=True)`

## `PhotoSorter/backend/server/workers/media_prepare.py`

Blob `d8915d8c29711bd9ff2c167eb7d39aaae4772f4a`; 141 lines.

- L7: `from app.config import DATA_DIR`
- L12: `import subprocess`
- L41: `rows = db.execute("""SELECT id,filename,target_path,original_media_type,declared_size`
- L45: `root = DATA_DIR / 'uploads' / str(batch_id)`
- L48: `dest.mkdir(exist_ok=True)`
- L56: `try:meta=probe(owned_file(Path(row['target_path']),root))`
- L57: `except (OSError,ValueError,subprocess.SubprocessError):pass`
- L88: `partial.unlink(missing_ok=True)`
- L92: `source = owned_file(Path(row['target_path']), root)`
- L93: `usage=shutil.disk_usage(dest)`
- L94: `if usage.free-max(64*1024**2,source.stat().st_size)<disk_guard.reserve(usage.total):`
- L100: `with partial.open('rb') as file:os.fsync(file.fileno())`
- L102: `os.replace(partial, output)`
- L110: `partial.unlink(missing_ok=True)`

## `PhotoSorter/backend/server/media/video.py`

Blob `fc03f2176da6f3081d6a5c9e2ee7f6bc66fe7c79`; 161 lines.

- L4: `import subprocess`
- L30: `with tempfile.TemporaryFile() as errors,tempfile.TemporaryFile() as output:`
- L32: `with subprocess.Popen(args, stdin=subprocess.DEVNULL,`
- L33: `stdout=output if progress else subprocess.DEVNULL, stderr=errors) as process:`
- L86: `with tempfile.TemporaryFile() as index:`
- L91: `with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=index, stderr=subprocess.DEVNULL) as proc:`
- L151: `frames = sorted(directory.glob('*.jpg'))`

## `PhotoSorter/backend/app/results/exporter.py`

Blob `561b4ca25d8649e6562842ded6ff83f9c07b2124`; 53 lines.

- L15: `path.parent.mkdir(parents=True, exist_ok=True)`
- L18: `fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)`
- L22: `file.write(payload)`
- L25: `os.replace(temp, path)`
- L32: `temp.unlink(missing_ok=True)`
- L38: `with (model_dir/'manifest.rows.jsonl').open('w',encoding='utf-8') as stream:`
- L40: `stream.write(json.dumps({'index':index,**row},ensure_ascii=False,separators=(',',':'))+'\n')`
- L41: `with (model_dir/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:`

## `PhotoSorter/backend/app/results/repository.py`

Blob `cc9b48697b44b727495cc40c2e8def33375366ea`; 67 lines.

- L4: `from ..config import RUNS_DIR`
- L11: `return RUNS_DIR/run_id`
- L18: `return json.loads(file.read_text('utf-8'))`
- L22: `if not RUNS_DIR.is_dir():return rows`
- L23: `for folder in RUNS_DIR.iterdir():`
- L31: `output.parent.mkdir(parents=True,exist_ok=True)`
- L34: `if staging.exists():shutil.rmtree(staging)`
- L50: `os.rename(staging,output)`
- L52: `if staging.exists():shutil.rmtree(staging)`
- L55: `index.mkdir(parents=True,exist_ok=True)`
- L65: `index=json.loads(path.read_text('utf-8'))`
- L66: `return json.loads(Path(index['path']).read_text('utf-8'))`

## `PhotoSorter/backend/app/jobs/runtime.py`

Blob `1e25c6b59c5fc7cbad23bec893bf06d35b67e3b1`; 69 lines.

- L23: `def save(self):`
- L42: `self.info['status']='running';self.save()`
- L60: `(self.path/'errors.txt').write_text(traceback.format_exc(),encoding='utf-8')`
- L67: `self.save();self.log('INFO',f'Завершено: {self.info["status"]}')`

## `PhotoSorter/backend/server/services/archive_cache.py`

Blob `972b44c7f1546c484c92e55bb154f106440dab91`; 109 lines.

- L24: `directory.mkdir(parents=True,exist_ok=True)`
- L25: `fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)`
- L27: `fcntl.flock(fd,fcntl.LOCK_SH)`
- L48: `fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)`
- L50: `fcntl.flock(fd,fcntl.LOCK_EX)`
- L51: `total,available=disk_guard.stat(root)`
- L62: `fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)`
- L69: `fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)`
- L76: `info=os.stat(name,dir_fd=fd,follow_symlinks=False)`
- L85: `os.stat(name[:-5]+".zip",dir_fd=fd,follow_symlinks=False)`
- L89: `os.unlink(name,dir_fd=fd)`

## `PhotoSorter/backend/server/services/archives.py`

Blob `f48549cd67bbc6baa22940bbcd51132d24fb0143`; 116 lines.

- L35: `run=owned_directory(storage_paths.run_dir(run_id,root),root)`
- L55: `info=file.stat()`
- L60: `folder=owned_directory(storage_paths.run_dir(run_id,root)/".archives",root)`
- L62: `folder.mkdir(parents=True,exist_ok=True)`
- L68: `total=sum(source.stat().st_size for source,_ in selected)`
- L70: `with archive_cache.pin(target.parent), os.fdopen(os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600),"a+b") as handle:`
- L71: `fcntl.flock(handle.fileno(),fcntl.LOCK_EX)`
- L79: `target.unlink()`
- L83: `fcntl.flock(handle.fileno(),fcntl.LOCK_UN)`
- L86: `fd,tmp=tempfile.mkstemp(dir=target.parent,prefix=".archive-",suffix=".tmp")`
- L89: `with zipfile.ZipFile(output,mode="w",compression=zipfile.ZIP_STORED,`
- L97: `archive.write(source,arcname=name,compress_type=zipfile.ZIP_STORED)`
- L98: `done+=source.stat().st_size`
- L101: `os.fsync(output.fileno())`
- L104: `with zipfile.ZipFile(tmp,"r") as verified:`
- L112: `os.replace(tmp,target)`
- L115: `Path(tmp).unlink(missing_ok=True)`

Failed fetches: none
