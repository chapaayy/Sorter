# Baseline source-site candidates — installation, infrastructure and host maintenance

Pinned SHA: c6d77ebb1c9c80c732df209a17a993dd38ec381f. Lexical candidate index, not semantic review or proof of complete runtime coverage. Includes false positives and misses possible indirect/native calls. No runtime data accessed.

## `install.sh`

Blob `d299fb92b49a961b04ab2b61ab61a97b7c057966`; 228 lines.

- L7: `echo "Usage: ./install.sh [--check | --deploy]"`
- L9: `echo "  --deploy: install missing prerequisites on Ubuntu/Debian, then deploy Sorter"`
- L12: `if [[ "$MODE" != "--check" && "$MODE" != "--deploy" ]]; then usage >&2; exit 2; fi`
- L14: `if [[ "$MODE" == "--check" ]]; then echo '[ERROR] .env missing' >&2; exit 1; fi`
- L15: `cp .env.example .env`
- L20: `if ! source .env 2>/dev/null; then`
- L21: `echo '[ERROR] Cannot read .env. Check its syntax.' >&2`
- L26: `echo 'Set a real hostname in .env: DOMAIN=sorter.yourdomain.com' >&2`
- L30: `echo '[ERROR] Set ADMIN_PASSWORD in .env (16–256 characters).' >&2`
- L34: `if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1 ||`
- L35: `! command -v python3 >/dev/null; then`
- L37: `echo '[ERROR] Docker Engine, Compose v2 and Python 3 are required. --check installs nothing.' >&2`
- L42: `if ! docker info --format '{{.ServerVersion}}' >/dev/null; then`
- L43: `echo '[ERROR] Cannot reach Docker Engine. Check that it is running and accessible to this user.' >&2`
- L51: `if docker volume inspect outdoor-sorter_postgres_data >/dev/null 2>&1; then`
- L56: `echo '[ERROR] Existing PostgreSQL volume but .env.generated is missing.' >&2`
- L57: `echo 'Restore the ORIGINAL credentials from your backup; do not regenerate.' >&2`
- L60: `if [[ "$MODE" == "--check" ]]; then echo '[ERROR] .env.generated missing' >&2; exit 1; fi`
- L61: `(umask 077; python3 - <<'PY' > .env.generated`
- L71: `echo '[ERROR] .env.generated incomplete; restore correct credentials.' >&2`
- L99: `COMPOSE=(docker compose --env-file .env --env-file .env.generated)`
- L111: `if b<a or b-a>255:raise ValueError()`
- L121: `echo '[ERROR] Set PHOTOSORTER_WORKER_CPUSET to valid CPU IDs before deployment.' >&2`
- L134: `chmod 600 .env .env.generated`
- L139: `ACTIVE_TCP_CC="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"`
- L142: `*) echo '[WARN] Could not determine host TCP algorithm; Caddy uses default CUBIC.' >&2 ;;`
- L145: `mkdir -p Models/models/megaloc Models/cache/huggingface/{hub,xet} Models/cache/{torch,xdg,downloads} PhotoSorter/data/{references,uploads,runs,cache,outputs}`
- L149: `chown -R 10001:10001 Models PhotoSorter/data`
- L151: `docker run --rm -v "$(pwd)/Models:/models" -v "$(pwd)/PhotoSorter/data:/data" alpine:3.21 sh -c 'chown -R 10001:10001 /models /data'`
- L154: `echo '[INFO] Skipped recursive chown of existing model/photo storage.'`
- L158: `[[ -d /run/systemd/system ]] && command -v systemctl >/dev/null; then`
- L159: `mkdir -p /var/lib/map-updater`
- L161: `exec 9>/var/lib/map-updater/deploy.lock`
- L166: `python3 PhotoSorter/tools/maintenance/map_build.py "$PWD" "$(git rev-parse HEAD)"`
- L178: `command -v systemctl >/dev/null 2>&1 &&`
- L181: `cat > "$AUDIT_UNIT" <<EOF`
- L184: `After=docker.service`
- L185: `Wants=docker.service`
- L205: `echo '[WARN] Could not start MAP filesystem observer; host snapshot audit still works.' >&2`
- L216: `echo '[WARN] Host audit reported coverage gaps; view Administration > Host audit.' >&2`

## `compose.yaml`

Blob `4abb6a64b0e442a3f1a57314ebde68112e1ffefb`; 153 lines.

- L3: `DATABASE_URL: postgresql://sorter:${POSTGRES_PASSWORD:?Run install.sh first}@postgres:5432/sorter`
- L18: `- /var/lib/map-updater/control:/run/map-updater:ro`
- L39: `- ./PhotoSorter/docker/caddy/Caddyfile:/etc/caddy/Caddyfile:ro`
- L52: `dockerfile: PhotoSorter/docker/app/Dockerfile`
- L61: `- /var/lib/map-updater/control:/run/map-updater:ro`
- L62: `- /var/lib/map-updater/rpc:/run/map-updater-rpc:ro`
- L79: `dockerfile: PhotoSorter/docker/app/Dockerfile`
- L97: `dockerfile: PhotoSorter/docker/app/Dockerfile`
- L115: `dockerfile: PhotoSorter/docker/app/Dockerfile`
- L135: `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Run install.sh first}`
- L137: `- postgres_data:/var/lib/postgresql/data`

## `PhotoSorter/docker/app/Dockerfile`

Blob `49945bf137e3b7d4fdfc0082df64adf3fd97eb7f`; 29 lines.

- L4: `COPY PhotoSorter/frontend/package.json PhotoSorter/frontend/package-lock.json ./`
- L5: `RUN npm ci --no-audit --no-fund`
- L6: `COPY PhotoSorter/frontend/tsconfig.json PhotoSorter/frontend/vite.config.ts PhotoSorter/frontend/index.html ./`
- L7: `COPY PhotoSorter/frontend/src ./src`
- L8: `COPY PhotoSorter/frontend/public ./public`
- L9: `RUN npm run build`
- L12: `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \`
- L14: `HOME=/workspace/Models/cache XDG_CACHE_HOME=/workspace/Models/cache/xdg \`
- L15: `HF_HOME=/workspace/Models/cache/huggingface HF_HUB_CACHE=/workspace/Models/cache/huggingface/hub \`
- L16: `HF_XET_CACHE=/workspace/Models/cache/huggingface/xet TORCH_HOME=/workspace/Models/cache/torch`
- L18: `RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates file ffmpeg && rm -rf /var/lib/apt/lists/*`
- L20: `RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu torchvision==0.29.1+cpu`
- L21: `COPY PhotoSorter/requirements-base.txt PhotoSorter/requirements.txt PhotoSorter/requirements-server.txt ./`
- L22: `RUN pip install -r requirements.txt -r requirements-server.txt`
- L23: `COPY PhotoSorter/backend ./backend`
- L24: `COPY PhotoSorter/frontend ./frontend`
- L25: `COPY --from=vue-build /ui/dist ./frontend/dist`
- L26: `ENV PYTHONPATH=/workspace/PhotoSorter/backend`
- L27: `USER 10001:10001`

## `PhotoSorter/docker/caddy/Caddyfile`

Blob `d0c13df062f1c9e812b70235c820ae6e13fa3d83`; 29 lines.



## `PhotoSorter/tools/maintenance/map_updater.py`

Blob `e6349a14b3f2e92fa2c122fdd8ccd2cd08cb36cd`; 408 lines.

- L14: `import subprocess`
- L23: `ROOT=Path("/var/lib/map-updater")`
- L43: `result=subprocess.run(args,cwd=cwd,timeout=timeout,env=env,`
- L44: `stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)`
- L55: `with temp.open("w",encoding="utf-8") as out:`
- L58: `os.fsync(out.fileno())`
- L60: `os.replace(temp,path)`
- L103: `(SELECT count(*) FROM archive_retries WHERE state='running')"""))`
- L131: `paths=[project,ROOT,Path("/var/lib/docker"),Path("/var/lib/containerd")]`
- L132: `return min(shutil.disk_usage(p).free for p in paths if p.exists())`
- L136: `directory.mkdir(mode=0o700)`
- L138: `shutil.copy2(project/name,directory/name)`
- L141: `with dump.open("wb") as stream:`
- L142: `subprocess.run(["docker","exec",service_id("postgres"),"pg_dump","-Fc",`
- L143: `"-U","sorter","-d","sorter"],stdout=stream,stderr=subprocess.PIPE,`
- L146: `os.fsync(stream.fileno())`
- L147: `with dump.open("rb") as stream:`
- L148: `subprocess.run(["docker","exec","-i",service_id("postgres"),"pg_restore","-l"],`
- L149: `stdin=stream,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,`
- L169: `except (RuntimeError,OSError,subprocess.SubprocessError):`
- L179: `self.state=json.loads(STATE.read_text())`
- L257: `locked=(ROOT/"deploy.lock").open("a")`
- L258: `fcntl.flock(locked,fcntl.LOCK_EX|fcntl.LOCK_NB)`
- L271: `if not any(m.get("Source")==str(CONTROL) and m.get("Destination")=="/run/map-updater"`
- L274: `docker("exec",service_id(service),"test","-f","/run/map-updater/activity.lock")`
- L276: `before=shutil.disk_usage(self.project).free`
- L279: `with tempfile.TemporaryDirectory(prefix="source-",dir=PRIVATE) as directory:`
- L281: `with archive.open("wb") as out:`
- L282: `subprocess.run(["git","archive","--format=tar",target],cwd=self.project,`
- L284: `subprocess.run(["tar","-xf",str(archive),"-C",directory],check=True,timeout=120)`
- L285: `archive.unlink()`
- L289: `MARKER.touch(mode=0o644,exist_ok=False)`
- L291: `gate=LOCK.open("rb")`
- L295: `fcntl.flock(gate,fcntl.LOCK_EX|fcntl.LOCK_NB)`
- L331: `except (RuntimeError,OSError,ValueError,http.client.HTTPException,subprocess.SubprocessError):`
- L339: `for path in PRIVATE.glob("backup-*"):`
- L341: `shutil.rmtree(path)`
- L344: `after=shutil.disk_usage(self.project).free`
- L345: `MARKER.unlink()`
- L359: `MARKER.unlink(missing_ok=True)`
- L380: `self.wfile.write((json.dumps(result,ensure_ascii=False)+"\n").encode())`
- L392: `if project.stat().st_uid!=0 or project.stat().st_mode&0o022:`
- L395: `socket_path.unlink(missing_ok=True)`
- L404: `socket_path.unlink(missing_ok=True)`

## `PhotoSorter/tools/maintenance/map_build.py`

Blob `fc4a616b83f24cf070de3fa1e06b7ca76ac72548`; 57 lines.

- L4: `import subprocess`
- L8: `STATE=Path("/var/lib/map-updater/private/builders")`
- L13: `subprocess.run(args,cwd=cwd,timeout=timeout,check=True)`
- L16: `STATE.mkdir(parents=True,exist_ok=True,mode=0o700)`
- L23: `marker.unlink()`
- L24: `except (OSError,subprocess.SubprocessError):`
- L34: `marker.touch(mode=0o600,exist_ok=False)`
- L44: `marker.unlink()`
- L45: `except (OSError,subprocess.SubprocessError):`

## `PhotoSorter/tools/maintenance/install_map_updater.sh`

Blob `2ddf5d5f26be7e7b64024d189b17a5b897f7ae1f`; 36 lines.

- L6: `install -d -o root -g root -m 0755 /var/lib/map-updater /var/lib/map-updater/control /var/lib/map-updater/rpc /usr/local/lib/map-updater`
- L7: `install -d -o root -g root -m 0700 /var/lib/map-updater/private`
- L9: `touch /var/lib/map-updater/control/activity.lock`
- L10: `chown root:root /var/lib/map-updater/control/activity.lock`
- L11: `chmod 0644 /var/lib/map-updater/control/activity.lock`
- L12: `install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/map_updater.py" /usr/local/lib/map-updater/map_updater.py`
- L13: `install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/map_build.py" /usr/local/lib/map-updater/map_build.py`
- L14: `cat > /etc/systemd/system/map-updater.service <<EOF`
- L17: `After=docker.service`
- L18: `Requires=docker.service`
- L26: `ExecStart=/usr/bin/python3 /usr/local/lib/map-updater/map_updater.py --project-root $ROOT`

## `PhotoSorter/tools/maintenance/snapshot.py`

Blob `cb70833a958c0ea1469f7c44f4823a63715f0bdf`; 309 lines.

- L16: `import subprocess`
- L29: `with Path(path).open("rb") as stream:`
- L37: `env=os.environ.copy()`
- L53: `return subprocess.run(args,env=env,check=True,stdout=subprocess.PIPE if capture else subprocess.DEVNULL,`
- L54: `stderr=subprocess.PIPE)`
- L85: `for p in sorted(folder.rglob("*")):`
- L106: `with tarfile.open(tar_path,"w",format=tarfile.PAX_FORMAT) as tar:`
- L110: `before=path.lstat()`
- L135: `with path.open("rb") as stream:tar.addfile(info,stream)`
- L141: `after=path.lstat()`
- L155: `destination.parent.mkdir(parents=True,exist_ok=True)`
- L156: `scratch=Path(tempfile.mkdtemp(prefix=".photosorter-backup-",dir=destination.parent))`
- L169: `(scratch/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf8")`
- L172: `scratch.rename(destination)`
- L175: `shutil.rmtree(scratch)`
- L180: `manifest=json.loads((archive/"manifest.json").read_text(encoding="utf8"))`
- L189: `with tarfile.open(archive/"files.tar","r") as tar:`
- L231: `manifest=json.loads((archive/"manifest.json").read_text(encoding="utf8"))`
- L239: `if not marker.is_file() or marker.read_text(encoding="utf8").strip()!="STAGING_ONLY":`
- L246: `destination.mkdir(mode=0o700)`
- L248: `(destination/folder).mkdir(parents=True,exist_ok=True)`
- L250: `with tarfile.open(archive/"files.tar","r") as tar:`
- L254: `dest.parent.mkdir(parents=True,exist_ok=True)`
- L256: `with tar.extractfile(member) as src,dest.open("xb") as dst:`
- L257: `shutil.copyfileobj(src,dst,BLOCK)`
- L263: `os.link(origin,dest,follow_symlinks=False)`
- L266: `os.symlink(member.linkname,dest)`

## `PhotoSorter/tools/maintenance/audit_host.py`

Blob `2e6220d433e99fcbe221b0eef95a11d1df44d5bb`; 525 lines.

- L17: `import subprocess`
- L28: `DEFAULT_SHARED = ('/var/lib/containerd','/var/log','/var/cache/apt','/tmp','/var/tmp','/run')`
- L38: `response = subprocess.run(['docker',*args], stdout=subprocess.PIPE,`
- L39: `stderr=subprocess.PIPE, text=True, timeout=45)`
- L59: `name = link.read_text(encoding='ascii').strip()`
- L90: `self.containerd_root = Path(os.environ.get("PHOTOSORTER_CONTAINERD_ROOT", "/var/lib/containerd"))`
- L247: `info = entry or path.lstat()`
- L281: `def walk(self,writer,root,kind,owner,*,view=False):`
- L299: `for folder,dirs,files in os.walk(root,followlinks=False,onerror=fail):`
- L335: `result=subprocess.run(['dpkg-query','-L',package],capture_output=True,`
- L343: `except (OSError,subprocess.TimeoutExpired):`
- L359: `cg=(pidpath/'cgroup').read_text(errors='replace')`
- L374: `info=path.stat()`
- L386: `target.mkdir(parents=True,exist_ok=True)`
- L394: `fd,tmpcsv=tempfile.mkstemp(prefix='.host-audit-',suffix='.csv.tmp',dir=target)`
- L398: `self.walk(writer,self.project,'project',self.name)`
- L400: `self.walk(writer,self.docker_root,'docker_global','Docker')`
- L405: `self.walk(writer,root,'docker_external',name)`
- L408: `self.walk(writer,root,'image_external','MAP image')`
- L409: `for root in (Path('/var/lib/map-updater'),Path('/usr/local/lib/map-updater')):`
- L411: `self.walk(writer,root,'host_updater','MAP updater')`
- L416: `self.walk(writer,root,kind,name)`
- L420: `self.walk(writer,root,'shared_system','not MAP-specific')`
- L428: `self.walk(writer,root,'container_tmp_view',`
- L439: `fd,tmpwrites=tempfile.mkstemp(prefix='.host-audit-',suffix='.sites.tmp',dir=target)`
- L444: `if tmpwrites and os.path.exists(tmpwrites):`
- L445: `os.unlink(tmpwrites)`
- L491: `fd,tmpjson=tempfile.mkstemp(prefix='.host-audit-',suffix='.json.tmp',dir=target)`
- L494: `out.write('\n')`
- L497: `os.replace(tmpcsv,target/'latest.csv')`
- L500: `os.replace(tmpwrites,target/'latest-write-sites.csv')`
- L501: `os.replace(tmpjson,target/'latest.json')`
- L505: `if path and os.path.exists(path):`
- L506: `os.unlink(path)`

## `PhotoSorter/tools/maintenance/audit_live.py`

Blob `32c2e382917d64f8a06c07475e7198fced0fbf6e`; 423 lines.

- L21: `import subprocess`
- L56: `return subprocess.run(["docker", *args], capture_output=True, text=True,`
- L71: `raw = (proc_root / str(pid) / "mountinfo").read_text(encoding="utf-8")`
- L90: `Path("/var/lib/map-updater"), Path("/usr/local/lib/map-updater"),`
- L115: `return ("map_updater" if root in (Path("/var/lib/map-updater"), Path("/usr/local/lib/map-updater")) else`
- L137: `self.report.mkdir(parents=True, exist_ok=True)`
- L139: `data_gid=(self.project / "PhotoSorter" / "data").stat().st_gid`
- L145: `self.stream = (self.report / "live-events.jsonl").open("a", encoding="utf-8", buffering=1)`
- L149: `(self.project / "PhotoSorter" / "data").stat().st_gid)`
- L159: `self.stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")`
- L234: `with os.scandir(current) as iterator:`
- L257: `except (OSError, subprocess.SubprocessError, ValueError) as exc:`
- L320: `meta = path.lstat()`
- L363: `"Records include file metadata only and do not measure every write() syscall.",`
- L368: `temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")`
- L370: `os.replace(temp,self.report/"live-state.json")`

## `PhotoSorter/tools/maintenance/audit_containerd.py`

Blob `ad386bc8335a3707d55b67d36e5c2b1ff637572a`; 214 lines.

- L14: `import subprocess`
- L38: `results.append(("upper", upper.replace("\\040", " ")))`
- L41: `results.append(("lower", lower.replace("\\040", " ")))`
- L84: `result = subprocess.run(`
- L86: `stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,`
- L103: `ctr_available = shutil.which("ctr") is not None`
- L117: `raw = (proc_root / str(pid) / "mountinfo").read_text(encoding="utf-8")`
- L168: `except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:`

## `PhotoSorter/tools/maintenance/ci_restore_drill.py`

Blob `2eefb6da605cc265b77d68600550e8f0f5da67f9`; 66 lines.

- L33: `with tempfile.TemporaryDirectory(prefix="photosorter-ci-restore-") as scratch:`
- L38: `a.mkdir(parents=True);b.mkdir(parents=True)`
- L39: `(root/"Models"/"models"/"megaloc").mkdir(parents=True)`
- L40: `(root/"Models"/"cache"/"torch"/"hub").mkdir(parents=True)`
- L41: `(root/".env.generated").write_text("POSTGRES_PASSWORD=test_only_no_real_data\nADMIN_PASSWORD=test_only_no_real_data\n")`
- L42: `(root/".env").write_text("DOMAIN=ci.example.test\n")`
- L43: `(root/"compose.yaml").write_text("name: staging-only\n")`
- L45: `original.write_bytes(data)`
- L46: `os.link(original,b/"ref.jpg")`
- L50: `(temp/".photosorter-staging-only").write_text("STAGING_ONLY")`
- L55: `assert result_a.read_bytes()==data and result_b.read_bytes()==data`
- L56: `assert result_a.stat().st_ino==result_b.stat().st_ino`

## `PhotoSorter/tools/maintenance/smoke_container.sh`

Blob `91ebe47bae3c25ce3998e3cfeda5a61aa7cde684`; 87 lines.

- L6: `echo '[BLOCKED] This test is permitted ONLY on ephemeral GitHub Actions runner.' >&2`
- L21: `mkdir -p Models/models/megaloc Models/cache/{torch,xdg,downloads,huggingface} PhotoSorter/data/{references,uploads,runs,cache,outputs}`
- L22: `sudo chown -R 10001:10001 Models PhotoSorter/data`
- L25: `docker compose ps || true`
- L26: `docker compose logs --tail=80 api worker thumbnail cleanup postgres caddy || true`
- L27: `docker compose down --remove-orphans || true`
- L31: `sudo install -d -m 0755 /var/lib/map-updater/control`
- L32: `sudo touch /var/lib/map-updater/control/activity.lock`
- L33: `sudo chmod 0644 /var/lib/map-updater/control/activity.lock`
- L34: `sudo install -d -o "$(id -u)" -g "$(id -g)" -m 0700 /var/lib/map-updater/private/builders`
- L35: `python3 PhotoSorter/tools/maintenance/map_build.py "$PWD" "$(git rev-parse HEAD)"`
- L36: `test -z "$(find /var/lib/map-updater/private/builders -type f -print -quit)"`
- L37: `docker compose up -d --no-build`
- L41: `if curl -kfsS --max-time 4 https://localhost/api/health >/dev/null 2>&1; then healthy=1;break;fi`
- L45: `echo "[ERROR] HTTPS/API failed to become ready" >&2`
- L48: `curl -kfsS --max-time 10 https://localhost/ | grep -Fq '<title>MAP</title>'`
- L49: `curl -kfsS --max-time 10 https://localhost/fo | grep -Fq '<title>MAP</title>'`
- L53: `cookie_file="$(mktemp)"`
- L54: `chmod 600 "$cookie_file"`
- L55: `trap 'rm -f "$cookie_file";cleanup' EXIT`
- L59: `--data-binary @- https://localhost/api/auth/login >/dev/null`
- L63: `if printf '%s' "$state" | python3 -c 'import json,sys;data=json.load(sys.stdin);roles=data.get("services",{});sys.exit(0 if all(roles.get(k,{}).get("alive") for k in ("megaloc","thumbnail","cleanup")) else 1)' 2>/dev/nul`
- L69: `echo "[ERROR] Worker heartbeat did not become healthy" >&2`
- L74: `sudo touch /var/lib/map-updater/control/maintenance`
- L76: `curl -kfsS --max-time 8 https://localhost/api/health >/dev/null`
- L77: `sudo rm /var/lib/map-updater/control/maintenance`
- L82: `id="$(printf '%s' "$created" | python3 -c 'import json,sys;print(json.load(sys.stdin)["batch_id"])')"`
- L83: `curl -kfsS --max-time 8 -b "$cookie_file" "https://localhost/api/batches/$id" >/dev/null`
- L85: `-H 'Origin: https://localhost' "https://localhost/api/batches/$id" >/dev/null`

Failed fetches: none
