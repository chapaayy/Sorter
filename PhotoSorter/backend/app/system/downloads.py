"""Safe explicit MegaLoc download; one job at a time and no hidden downloads."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from ..config import WEIGHTS_DIR, MODEL_CACHE_DIR
from . import model_store

LOG_DIR = MODEL_CACHE_DIR / 'downloads'

def folder_size(path):
    total = 0
    for root,_,names in os.walk(path):
        for name in names:
            try: total += (Path(root)/name).stat().st_size
            except OSError:pass
    return total

class Downloads:
    def __init__(self):
        self.lock=threading.RLock()
        self.states={}
        self.active=False

    def status(self):
        with self.lock:return {k:dict(v) for k,v in self.states.items()}

    def _set(self,status,message,**progress):
        with self.lock:self.states['megaloc']={'status':status,'message':str(message)[-1200:],**progress}

    def start(self,name):
        if name!='megaloc':raise ValueError('Доступна только MegaLoc')
        with self.lock:
            if self.active:raise RuntimeError('Загрузка MegaLoc уже выполняется')
            if model_store.verified():
                self._set('installed','MegaLoc уже проверена')
                return dict(self.states['megaloc'])
            self.active=True
            self._set('downloading','Подготовка загрузки…',stage='prepare')
            threading.Thread(target=self._run,daemon=True,name='megaloc-download').start()
            return dict(self.states['megaloc'])

    def _run(self):
        try:
            LOG_DIR.mkdir(parents=True,exist_ok=True)
            if not model_store.files_present():
                if not all((model_store.repo_folder()/name).is_file() for name in ('hubconf.py','megaloc_model.py')):
                    self._download_source()
                if model_store.checkpoint() is None:
                    self._download_weights()
            self._verify()
            model_store.remember_verified()
            self._set('installed','MegaLoc загружена и проверена',stage='done')
        except Exception as exc:
            self._set('error',f'{type(exc).__name__}: {exc}',stage='error')
        finally:
            with self.lock:self.active=False

    def _download_weights(self):
        target=WEIGHTS_DIR/'megaloc'
        target.mkdir(parents=True,exist_ok=True)
        before=folder_size(target)
        log=LOG_DIR/'megaloc.log'
        cmd=[sys.executable,'-c',
             'import sys; from huggingface_hub import hf_hub_download; hf_hub_download(repo_id="gberton/MegaLoc",filename="model.safetensors",local_dir=sys.argv[1])',str(target)]
        env=os.environ.copy()
        env['HF_HUB_OFFLINE']='0'
        with log.open('w',encoding='utf8') as output:
            process=subprocess.Popen(cmd,env=env,stdout=output,stderr=subprocess.STDOUT)
            try:
                while process.poll() is None:
                    received=max(0,folder_size(target)-before)
                    self._set('downloading',f'Веса MegaLoc: {received/1024/1024:.1f} МБ',stage='weights',received_bytes=received)
                    time.sleep(1)
                code=process.wait()
            finally:
                if process.poll() is None:process.terminate()
        if code:raise RuntimeError('Ошибка загрузки весов: '+log.read_text('utf8',errors='replace')[-1200:])
        if model_store.checkpoint() is None:raise RuntimeError('Веса загружены не полностью')

    def _download_source(self):
        target=MODEL_CACHE_DIR/'torch'/'hub'/model_store.SOURCE_FOLDER
        stage=LOG_DIR/'megaloc-source.staging'
        temp=LOG_DIR/'megaloc-source.zip.part'
        if stage.exists():shutil.rmtree(stage)
        stage.mkdir(parents=True)
        url='https://github.com/gmberton/MegaLoc/archive/refs/heads/main.zip'
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'PhotoSorter/4.0'})
            with urllib.request.urlopen(request,timeout=45) as response, temp.open('wb') as file:
                amount=0
                while True:
                    chunk=response.read(256*1024)
                    if not chunk:break
                    amount+=len(chunk)
                    if amount>90_000_000:raise RuntimeError('Исходники больше 90 МБ')
                    file.write(chunk)
                    self._set('downloading',f'Исходники MegaLoc: {amount/1024/1024:.1f} МБ',stage='source',received_bytes=amount)
            total=0
            with zipfile.ZipFile(temp) as archive:
                for entry in archive.infolist():
                    if entry.is_dir():continue
                    parts=PurePosixPath(entry.filename).parts
                    if len(parts)<2:continue
                    relative=PurePosixPath(*parts[1:])
                    if relative.is_absolute() or '..' in relative.parts:
                        raise RuntimeError('Небезопасный путь внутри исходников')
                    if relative.suffix!='.py' and relative.name not in ('LICENSE','LICENSE.txt'):continue
                    if ((entry.external_attr>>16)&0o170000)==0o120000:
                        raise RuntimeError('Символические ссылки не поддерживаются')
                    total+=entry.file_size
                    if total>35_000_000:raise RuntimeError('Исходники превышают ограничение размера')
                    destination=stage.joinpath(*relative.parts)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    with archive.open(entry) as src, destination.open('wb') as dst:shutil.copyfileobj(src,dst)
            if not all((stage/name).is_file() for name in ('hubconf.py','megaloc_model.py')):
                raise RuntimeError('В архиве нет исходного кода MegaLoc')
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():stage.rename(target)
            else:
                for file in stage.rglob('*'):
                    if file.is_file():
                        dst=target/file.relative_to(stage)
                        if not dst.exists():
                            dst.parent.mkdir(parents=True,exist_ok=True)
                            shutil.copy2(file,dst)
        finally:
            temp.unlink(missing_ok=True)
            if stage.exists():shutil.rmtree(stage)

    def _verify(self):
        self._set('verifying','Проверяем реальную загрузку MegaLoc на CPU…',stage='verify')
        backend=Path(__file__).resolve().parents[2]
        log=LOG_DIR/'megaloc.verify.log'
        source=('import sys;sys.path.insert(0,sys.argv[1]);'
                'from app.recognition.engines.megaloc.extractor import MegaLocEngine;'
                'model=MegaLocEngine();assert model.net is not None;model.unload();print("MODEL_OK")')
        with log.open('w',encoding='utf8') as output:
            result=subprocess.run([sys.executable,'-c',source,str(backend)],stdout=output,stderr=subprocess.STDOUT,timeout=420)
        if result.returncode or 'MODEL_OK' not in log.read_text('utf8',errors='replace'):
            raise RuntimeError('Веса найдены, но MegaLoc не загрузилась: '+log.read_text('utf8',errors='replace')[-1300:])

downloads=Downloads()
