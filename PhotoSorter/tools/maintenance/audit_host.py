#!/usr/bin/env python3
"""Read-only MAP host disk audit. Only latest report files are replaced.

Requires root to inspect Docker volumes, overlay layers and /proc. Filesystem
metadata only: never opens application data, secrets or database contents.
This is a point-in-time census, NOT a lossless log of transient file events.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = ('path','scope','category','owner','kind','logical_bytes',
           'allocated_bytes','hardlink_reused','link_count','device','inode','modified_utc')
DEFAULT_SHARED = ('/var/lib/containerd','/var/log','/var/cache/apt','/tmp','/var/tmp','/run')

def within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

def docker(*args):
    response = subprocess.run(['docker',*args], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=45)
    if response.returncode:
        raise RuntimeError('Docker command failed: '+ ' '.join(args[:2])
                           +' '+response.stderr.strip()[:160])
    return response.stdout

def layers(root, images, warnings):
    """Identify immutable overlay2 layers of MAP images by Docker diff chain IDs."""
    found = set()
    for image in images:
        previous = ''
        for diff in image.get('RootFS',{}).get('Layers',[]) or []:
            if not diff.startswith('sha256:'):
                warnings.append('Unknown image diff digest')
                continue
            chain = diff if not previous else 'sha256:' + hashlib.sha256(
                (previous+' '+diff).encode('ascii')).hexdigest()
            previous = chain
            link = root/'image'/'overlay2'/'layerdb'/'sha256'/chain[7:]/'cache-id'
            try:
                name = link.read_text(encoding='ascii').strip()
                if not re.fullmatch(r'[a-zA-Z0-9_-]+',name):
                    raise ValueError('Invalid layer identifier')
                found.add(root/'overlay2'/name/'diff')
            except (OSError,ValueError):
                warnings.append('Cannot attribute image layer '+chain[-12:])
    return sorted(found)

class HostAudit:
    def __init__(self, project, *, project_name='outdoor-sorter',
                 call=docker, shared_roots=None, proc_root=Path('/proc')):
        self.project = Path(project).resolve(strict=True)
        self.name = project_name
        self.call = call
        self.shared_roots = [Path(p) for p in (DEFAULT_SHARED if shared_roots is None else shared_roots)]
        self.proc_root = Path(proc_root)
        self.output = self.project/'PhotoSorter'/'data'/'audits'/'host'
        self.errors = []
        self.count = 0
        self.skipped = 0
        self.scopes = defaultdict(lambda: {'files':0,'allocated_bytes':0,'logical_bytes':0})
        self.categories = defaultdict(lambda: {'files':0,'allocated_bytes':0,'logical_bytes':0,'hardlink_paths':0})
        self.inodes = set()
        self.containers = []
        self.docker_root = None
        self.docker_driver = None
        self.docker_global = []
        self.project_volumes = []
        self.project_uppers = []
        self.project_containers = []
        self.project_layers = []
        self.containerd_root = Path(os.environ.get("PHOTOSORTER_CONTAINERD_ROOT", "/var/lib/containerd"))
        self.containerd_snapshot_root = self.containerd_root / "io.containerd.snapshotter.v1.overlayfs"
        self.containerd_attribution = {"snapshots": {}, "warnings": ["Not yet discovered"]}
        self.containerd_snapshots = {}
        self.containerd_sizes = defaultdict(lambda: {"files": 0, "allocated_bytes": 0})
        self.additional_roots = []
        self.roots_checked = []
        self.mount_views_excluded = 0
        self.root_order = ('uploads','reference_staging','references','outputs',
                           'reference_exports','cache','runs','incoming','audits')

    def json(self,*args):
        return json.loads(self.call(*args))

    def discover(self):
        try:
            info = self.json('info','--format','{{json .}}')
            root = Path(info['DockerRootDir'])
            if not root.is_absolute() or root == Path('/'):
                raise ValueError('Invalid Docker root')
            self.docker_root = root
            self.docker_driver = info.get('Driver')
        except (RuntimeError,ValueError,OSError,KeyError) as exc:
            self.errors.append('Docker discovery: '+str(exc))
            return
        try:
            ids = self.call('ps','-aq','--filter',
                'label=com.docker.compose.project='+self.name).split()
            self.containers = self.json('inspect',*ids) if ids else []
        except (RuntimeError,ValueError) as exc:
            self.errors.append('Container discovery: '+str(exc))
        images = set()
        for container in self.containers:
            cid = container.get('Id','')
            name = container.get('Name','').lstrip('/') or cid[:12]
            if container.get('Image'):
                images.add(container['Image'])
            upper = container.get('GraphDriver',{}).get('Data',{}).get('UpperDir')
            if upper:
                self.project_uppers.append((Path(upper),name))
            if cid:
                self.project_containers.append((self.docker_root/'containers'/cid,name))
            log = container.get('LogPath')
            if log and self.docker_root and not within(Path(log),self.docker_root):
                self.additional_roots.append((Path(log),'container_log',name))
            for mount in container.get('Mounts',[]):
                if mount.get('Type')=='volume' and mount.get('Source'):
                    self.project_volumes.append((Path(mount['Source']),
                                                 mount.get('Name') or name))
        try:
            # Includes volumes from stopped project containers.
            names = set(self.call('volume','ls','-q','--filter',
                'label=com.docker.compose.project='+self.name).split())
            names.update(v for v in self.call('volume','ls','-q').split()
                         if v.startswith(self.name+'_'))
            if names:
                for v in self.json('volume','inspect',*sorted(names)):
                    if v.get('Mountpoint'):
                        self.project_volumes.append((Path(v['Mountpoint']),v['Name']))
        except (RuntimeError,ValueError) as exc:
            self.errors.append('Volume discovery: '+str(exc))
        try:
            img = self.json('image','inspect',*sorted(images)) if images else []
            if self.docker_driver=='overlay2':
                self.project_layers = layers(self.docker_root,img,self.errors)
            elif self.docker_driver == 'overlayfs':
                companion = Path(__file__).with_name("audit_containerd.py")
                spec = importlib.util.spec_from_file_location("map_audit_containerd", companion)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.containerd_attribution = module.collect(
                    self.containers, img, Path('/proc'), self.containerd_snapshot_root
                )
                self.containerd_snapshots = self.containerd_attribution["snapshots"]
                for warning in self.containerd_attribution["warnings"]:
                    self.errors.append("Containerd mapping: " + warning)
            elif images:
                self.errors.append('Unsupported Docker storage driver: ' + str(self.docker_driver))
        except (RuntimeError,ValueError) as exc:
            self.errors.append('Image discovery: '+str(exc))
        try:
            raw = self.call('system','df','--format','{{json .}}')
            self.docker_global = [json.loads(line) for line in raw.splitlines() if line]
        except (RuntimeError,ValueError) as exc:
            self.errors.append('Docker global usage: '+str(exc))

    def label(self,path,hint,owner):
        if hint in ('host_package_file','host_installer_config'):
            return ('shared_unattributed',hint,'Host dependencies (shared)','disk')
        if hint=='container_tmp_view':
            return ('runtime_view','container_tmp',owner,'non_additive_view')
        if hint=='container_root_view':
            return ('runtime_view','container_root_mount',owner,'non_additive_view')
        if hint=='open_deleted_fd':
            return ('app','open_deleted_file',owner,'disk')
        if within(path,self.project):
            rel = path.relative_to(self.project).parts
            if len(rel)>=3 and rel[:3]==('PhotoSorter','data','uploads'):
                cat = 'normalized' if len(rel)>4 and rel[4]=='.normalized' else 'originals'
            elif len(rel)>=3 and rel[:3]==('PhotoSorter','data','outputs'):
                if '.archives' in rel:
                    cat = 'results_zip' if path.suffix.lower()=='.zip' else 'results_temporary'
                elif any(p.endswith('.building') for p in rel):
                    cat = 'results_temporary'
                else:
                    cat = 'results'
            elif len(rel)>=3 and rel[:3]==('PhotoSorter','data','reference_staging'):
                cat = 'reference_uploads' if 'incoming' in rel else 'reference_objects'
            elif len(rel)>=3 and rel[:3]==('PhotoSorter','data','references'):
                cat = 'reference_gallery'
            elif len(rel)>=3 and rel[:3]==('PhotoSorter','data','reference_exports'):
                cat = 'reference_zip' if path.suffix.lower()=='.zip' else 'reference_export_temporary'
            elif len(rel)>=3 and rel[:3]==('PhotoSorter','data','cache'):
                cat = 'megaloc_cache' if 'megaloc' in rel else (
                    'thumbnails' if 'thumbnails' in rel else 'other_cache')
            elif len(rel)>=3 and rel[:3]==('PhotoSorter','data','runs'):
                cat = 'run_logs' if path.name.startswith('events.jsonl') else 'run_metadata'
            elif len(rel)>=3 and rel[:3]==('PhotoSorter','data','incoming'):
                cat = 'incomplete_uploads'
            elif len(rel)>=3 and rel[:3]==('PhotoSorter','data','audits'):
                cat = 'audit_reports'
            elif len(rel)>1 and rel[0]=='Models':
                cat = 'model_cache' if rel[1]=='cache' else 'model_weights'
            else:
                cat = 'app_source_installer_and_git'
            return ('app',cat,self.name,'disk')
        for root,name in self.project_volumes:
            if within(path,root):
                return ('app','docker_volume',name,'disk')
        for root,name in self.project_uppers:
            if within(path,root):
                return ('app','container_writable_layer',name,'disk')
        for root,name in self.project_containers:
            if within(path,root):
                return ('app','container_metadata_and_logs',name,'disk')
        for root in self.project_layers:
            if within(path,root):
                return ('app_shared_layer','docker_image_layer','MAP + shared images','disk')
        if within(path, self.containerd_snapshot_root):
            relative = path.relative_to(self.containerd_snapshot_root).parts
            if len(relative) >= 2 and relative[0] == 'snapshots':
                item = self.containerd_snapshots.get(relative[1])
                if item:
                    category = item["category"]
                    scope = 'app' if category == 'containerd_active_upper' else 'app_shared_layer'
                    return (scope, category, ', '.join(item["owners"])[:240], 'disk')
            return ('shared_unattributed','containerd_unattributed','Shared containerd','disk')
        if within(path, self.containerd_root):
            return ('shared_unattributed','containerd_content_or_metadata','Shared containerd','disk')
        if self.docker_root and within(path,self.docker_root):
            return ('shared_unattributed','docker_other','Docker global / build cache','disk')
        return ('shared_unattributed',hint,owner,'disk')

    def add(self,writer,path,kind,owner,*,view=False,display=None,entry=None):
        try:
            info = entry or path.lstat()
        except (OSError,ValueError):
            self.skipped += 1
            return
        if stat.S_ISREG(info.st_mode):
            file_kind = 'file'
        elif stat.S_ISDIR(info.st_mode):
            file_kind = 'directory'
        elif stat.S_ISLNK(info.st_mode):
            file_kind = 'symlink'
        else:
            file_kind = 'special'
        scope,category,who,storage = self.label(path,kind,owner)
        if view:
            storage = 'non_additive_view'
        inode=(info.st_dev,info.st_ino)
        already=inode in self.inodes
        if not view:
            self.inodes.add(inode)
        size=info.st_size
        allocated = 0 if view or already else info.st_blocks*512
        writer.writerow((display or str(path),scope,category,who,file_kind,size,
                         allocated,int(already),info.st_nlink,info.st_dev,
                         info.st_ino,datetime.fromtimestamp(info.st_mtime,timezone.utc).isoformat()))
        self.count += 1
        for counts in (self.scopes[scope],self.categories[category]):
            counts['files'] += 1
            counts['logical_bytes'] += size
            counts['allocated_bytes'] += allocated
        self.categories[category]['hardlink_paths'] += int(already)
        if category.startswith('containerd_'):
            self.containerd_sizes[category]['files'] += 1
            self.containerd_sizes[category]['allocated_bytes'] += allocated

    def walk(self,writer,root,kind,owner,*,view=False):
        root=Path(root)
        if root.is_symlink():
            self.skipped += 1
            self.errors.append('Root is symlink: '+str(root))
            return
        if not root.exists():
            self.errors.append('Root unavailable: '+str(root))
            return
        self.roots_checked.append({'path':str(root),'role':kind})
        if root.is_file():
            self.add(writer,root,kind,owner,view=view)
            return
        self.add(writer,root,kind,owner,view=view)
        def fail(exc):
            self.skipped += 1
            if len(self.errors)<100:
                self.errors.append('Unreadable: '+str(exc)[:180])
        for folder,dirs,files in os.walk(root,followlinks=False,onerror=fail):
            if self.docker_root and Path(folder).parent == self.docker_root/'overlay2':
                dirs[:]=[d for d in dirs if d!='merged']
            keep=[]
            for name in dirs:
                p=Path(folder)/name
                if p.is_symlink():
                    self.add(writer,p,kind,owner,view=view)
                elif (self.docker_root and
                      p.parent == self.docker_root/'rootfs'/'overlayfs' and p.is_mount()):
                    # Docker's containerd snapshotter exposes complete merged
                    # container rootfilesystems here. They are *views*, not new
                    # physical copies. Count the mountpoint, never its contents.
                    self.add(writer,p,'container_root_view',name,view=True)
                    self.mount_views_excluded += 1
                elif kind=='shared_system' and p.is_mount():
                    self.skipped += 1
                    if len(self.errors)<100:
                        self.errors.append('External mount not traversed: '+str(p))
                else:
                    keep.append(name)
            if Path(folder)==self.project/'PhotoSorter'/'data':
                priority={name:i for i,name in enumerate(self.root_order)}
                dirs[:]=sorted(keep,key=lambda name:(priority.get(name,100),name))
            else:
                dirs[:]=sorted(keep)
            for name in sorted(files):
                self.add(writer,Path(folder)/name,kind,owner,view=view)
            for name in dirs:
                self.add(writer,Path(folder)/name,kind,owner,view=view)

    def host_dependencies(self,writer):
        packages=('docker-ce','docker-ce-cli','containerd.io','docker-compose-plugin',
                  'docker-buildx-plugin','python3','python3-minimal')
        for package in packages:
            try:
                result=subprocess.run(['dpkg-query','-L',package],capture_output=True,
                                      text=True,check=False,timeout=15)
                if result.returncode:
                    continue
                for name in result.stdout.splitlines():
                    path=Path(name)
                    if path.is_absolute() and path.exists() and not path.is_dir():
                        self.add(writer,path,'host_package_file',package)
            except (OSError,subprocess.TimeoutExpired):
                self.errors.append('Could not list package: '+package)
        for path in ('/etc/apt/sources.list.d/docker.sources',
                     '/etc/apt/keyrings/docker.asc',
                     '/etc/sysctl.d/99-photosorter-bbr.conf',
                     '/etc/modules-load.d/99-photosorter-bbr.conf'):
            if Path(path).exists():
                self.add(writer,Path(path),'host_installer_config','Host setup')

    def deleted_fds(self,writer):
        identifiers=[c.get('Id','') for c in self.containers if c.get('Id')]
        pids=set(int(c.get('State',{}).get('Pid') or 0) for c in self.containers)
        for pidpath in self.proc_root.iterdir():
            if not pidpath.name.isdigit():
                continue
            try:
                cg=(pidpath/'cgroup').read_text(errors='replace')
                if any(cid in cg or cid[:12] in cg for cid in identifiers):
                    pids.add(int(pidpath.name))
            except OSError:
                pass
        for pid in sorted(p for p in pids if p>0):
            try:
                fds=list((self.proc_root/str(pid)/'fd').iterdir())
            except OSError:
                continue
            for path in fds:
                try:
                    name=os.readlink(path)
                    if not name.endswith(' (deleted)'):
                        continue
                    info=path.stat()
                    if stat.S_ISREG(info.st_mode):
                        self.add(writer,path,'open_deleted_fd','pid:'+str(pid),
                                 display='open-deleted:'+str(pid)+':'+path.name+':'+name,entry=info)
                except OSError:
                    pass

    def execute(self):
        self.discover()
        target=self.output
        if target.is_symlink():
            raise RuntimeError('Audit directory is a symlink')
        target.mkdir(parents=True,exist_ok=True)
        if not within(target.resolve(),self.project):
            raise RuntimeError('Audit output escaped the project')
        first=datetime.now(timezone.utc)
        tmpcsv=tmpjson=tmpwrites=None
        write_sites_count=0
        start=time.monotonic()
        try:
            fd,tmpcsv=tempfile.mkstemp(prefix='.host-audit-',suffix='.csv.tmp',dir=target)
            with os.fdopen(fd,'w',encoding='utf-8-sig',newline='') as out:
                writer=csv.writer(out,delimiter=';',lineterminator='\n')
                writer.writerow(COLUMNS)
                self.walk(writer,self.project,'project',self.name)
                if self.docker_root and self.docker_root.is_dir():
                    self.walk(writer,self.docker_root,'docker_global','Docker')
                else:
                    self.errors.append('Docker root not scanned')
                for root,name in (self.project_volumes+self.project_uppers+self.project_containers):
                    if not (self.docker_root and within(root,self.docker_root)):
                        self.walk(writer,root,'docker_external',name)
                for root in self.project_layers:
                    if not (self.docker_root and within(root,self.docker_root)):
                        self.walk(writer,root,'image_external','MAP image')
                for root,kind,name in self.additional_roots:
                    self.walk(writer,root,kind,name)
                for root in self.shared_roots:
                    if root.is_dir() and not within(root,self.project) and not (
                        self.docker_root and within(root,self.docker_root)):
                        self.walk(writer,root,'shared_system','not MAP-specific')
                for container in self.containers:
                    pid=int(container.get('State',{}).get('Pid') or 0)
                    if not pid:
                        continue
                    for rel in ('tmp','var/tmp','dev/shm'):
                        root=self.proc_root/str(pid)/'root'/rel
                        if root.is_dir() and not root.is_symlink():
                            self.walk(writer,root,'container_tmp_view',
                                      container.get('Name','').lstrip('/'),view=True)
                self.host_dependencies(writer)
                self.deleted_fds(writer)
            # List the *potential* writes in source code as a second audit.
            # It never opens photos, references or model files.
            try:
                module_path=Path(__file__).with_name('audit_write_sites.py')
                spec=importlib.util.spec_from_file_location('map_audit_write_sites',module_path)
                module=importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                fd,tmpwrites=tempfile.mkstemp(prefix='.host-audit-',suffix='.sites.tmp',dir=target)
                os.close(fd)
                write_sites_count=module.export_csv(self.project,Path(tmpwrites))
            except (OSError,RuntimeError,ImportError,ValueError) as exc:
                self.errors.append('Source write-site inventory failed: '+str(exc)[:200])
                if tmpwrites and os.path.exists(tmpwrites):
                    os.unlink(tmpwrites)
                tmpwrites=None
            report={
                'schema':'map-host-audit-v1',
                'snapshot_id':uuid.uuid4().hex,
                'captured_at':first.isoformat(),
                'project':self.name,
                'files_scanned':self.count,
                'allocated_bytes':sum(v['allocated_bytes'] for v in self.scopes.values()),
                'scopes':dict(self.scopes),
                'categories':dict(self.categories),
                'checked_roots':self.roots_checked,
                'skipped_paths':self.skipped,
                'errors':self.errors,
                'scan_seconds':round(time.monotonic()-start,2),
                'container_root_mounts_excluded':self.mount_views_excluded,
                'write_sites_count':write_sites_count,
                'containerd_attribution': {
                    'driver': self.docker_driver,
                    'matched_snapshots': len(self.containerd_snapshots),
                    'container_mount_references': self.containerd_attribution.get('container_mount_references', 0),
                    'image_chains_checked': self.containerd_attribution.get('image_chains_checked', 0),
                    'image_chains_matched': self.containerd_attribution.get('image_chains_matched', 0),
                    'categories': dict(self.containerd_sizes),
                    'snapshot_owners': self.containerd_snapshots,
                    'warnings': self.containerd_attribution.get('warnings', []),
                    'limitations': self.containerd_attribution.get('limitations', []),
                },
                'docker':{
                    'containers':len(self.containers),
                    'volumes':len(set(str(x[0]) for x in self.project_volumes)),
                    'driver':self.docker_driver,
                    'matched_image_layers':len(self.project_layers),
                    'global_shared_disk_usage':self.docker_global,
                },
                'limitations':[
                    'Point-in-time snapshot: files already created and removed cannot be recovered.',
                    'Shared system and Docker BuildKit files are listed but not assigned entirely to MAP.',
                    'Container tmp and merged container root views do not add duplicate physical bytes.',
                    'Concurrent file updates can change sizes during the scan.',
                    'Neither contents nor database records are read.',
                    'Code-write-site report lists candidates, not guaranteed runtime paths.',
                ],
            }
            fd,tmpjson=tempfile.mkstemp(prefix='.host-audit-',suffix='.json.tmp',dir=target)
            with os.fdopen(fd,'w',encoding='utf-8') as out:
                json.dump(report,out,ensure_ascii=False,indent=2)
                out.write('\n')
            os.chmod(tmpcsv,0o644)
            os.chmod(tmpjson,0o644)
            os.replace(tmpcsv,target/'latest.csv')
            if tmpwrites:
                os.chmod(tmpwrites,0o644)
                os.replace(tmpwrites,target/'latest-write-sites.csv')
            os.replace(tmpjson,target/'latest.json')
            return report
        finally:
            for path in (tmpcsv,tmpjson,tmpwrites):
                if path and os.path.exists(path):
                    os.unlink(path)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',required=True,type=Path)
    parser.add_argument('--project-name',default='outdoor-sorter')
    options=parser.parse_args()
    if os.geteuid()!=0:
        parser.error('Use sudo/root: Docker and process files require host permissions')
    report=HostAudit(options.project_root,project_name=options.project_name).execute()
    print('Files:',report['files_scanned'],'allocated bytes:',report['allocated_bytes'],
          'skipped:',report['skipped_paths'])
    print('Report:',Path(options.project_root)/'PhotoSorter/data/audits/host/latest.csv')
    if report['errors']:
        print('Coverage warnings:',len(report['errors']),file=sys.stderr)
    return 0 if not report['errors'] else 2

if __name__=='__main__':
    sys.exit(main())
