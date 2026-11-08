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

OPTIONAL_INSTALLERS={
    'xfeat':('app.screen_detection.cli','--install'),
    'dinov2':('app.ad_recognition.cli','--install-dino'),
    'paddleocr':('app.ad_recognition.cli','--install-ocr'),
}

def optional_available(name):
    if name=='xfeat':
        from app.screen_detection import xfeat_assets
        return xfeat_assets.status()['available']
    if name=='dinov2':
        from app.ad_recognition import dino
        return dino.status()['available']
    if name=='paddleocr':
        from app.ad_recognition import ocr
        return ocr.status()['available']
    raise ValueError('Неизвестная модель')

def optional_size(name):
    if name=='xfeat':
        return folder_size(WEIGHTS_DIR/'xfeat')+folder_size(MODEL_CACHE_DIR/'xfeat')
    if name=='dinov2':
        return folder_size(WEIGHTS_DIR/'dinov2')
    if name=='paddleocr':
        return folder_size(WEIGHTS_DIR/'paddleocr')+folder_size(MODEL_CACHE_DIR/'paddlex')
    return 0


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
        if name!='megaloc' and name not in OPTIONAL_INSTALLERS:
            raise ValueError('Неизвестная модель')
        with self.lock:
            if self.active:
                raise RuntimeError('Дождитесь завершения установки предыдущей модели')
            installed=(model_store.verified() if name=='megaloc' else optional_available(name))
            if installed:
                if name=='megaloc':
                    self._set('installed','MegaLoc уже проверена')
                else:
                    self.states[name]={'status':'installed','stage':'done',
                                       'message':'Файлы модели проверены'}
                return dict(self.states[name])
            self.active=True
            if name=='megaloc':
                self._set('downloading','Подготовка загрузки…',stage='prepare')
                target=self._run
            else:
                self.states[name]={'status':'downloading','stage':'prepare',
                    'message':'Подготовка скачивания…','received_bytes':0}
                target=lambda:self._run_optional(name)
            threading.Thread(target=target,daemon=True,name=name+'-download').start()
            return dict(self.states[name])

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

    def _set_optional(self,name,status,message,**progress):
        with self.lock:
            self.states[name]={'status':status,'message':str(message)[-900:],**progress}

    def _run_optional(self,name):
        """One allowed pinned CPU installer at a time, in a subprocess."""
        import fcntl
        command=OPTIONAL_INSTALLERS[name]
        try:
            LOG_DIR.mkdir(parents=True,exist_ok=True)
            lock=LOG_DIR/'optional-installer.lock'
            with lock.open('a+b') as handle:
                try:
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise RuntimeError('Другой процесс уже устанавливает модель') from exc
                baseline=optional_size(name)
                logfile=LOG_DIR/(name+'.log')
                self._set_optional(name,'downloading','Скачивание и проверка файлов…',
                                   stage='download',received_bytes=0)
                started=time.monotonic()
                with logfile.open('w',encoding='utf-8') as output:
                    proc=subprocess.Popen([sys.executable,'-m',*command],
                        stdout=output,stderr=subprocess.STDOUT)
                    try:
                        while proc.poll() is None:
                            elapsed=time.monotonic()-started
                            if elapsed>3600:
                                proc.terminate()
                                raise TimeoutError('Установка превысила один час')
                            received=max(0,optional_size(name)-baseline)
                            self._set_optional(name,'downloading',
                                'Скачивание и подготовка модели…',
                                stage='download',received_bytes=received,
                                elapsed_seconds=round(elapsed))
                            time.sleep(1)
                        if proc.wait()!=0:
                            raise RuntimeError('Ошибка установки: '+
                                logfile.read_text('utf-8',errors='replace')[-800:])
                    finally:
                        if proc.poll() is None:
                            proc.terminate()
                self._set_optional(name,'verifying','Проверка контрольных сумм…',
                                   stage='verify',
                                   received_bytes=max(0,optional_size(name)-baseline))
                if not optional_available(name):
                    raise RuntimeError('Установка завершилась, но проверка модели не прошла')
                self._set_optional(name,'installed','Модель установлена и проверена',
                                   stage='done',received_bytes=max(0,optional_size(name)-baseline))
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        except Exception as exc:
            self._set_optional(name,'error',f'{type(exc).__name__}: {exc}',stage='error')
        finally:
            with self.lock:
                self.active=False

    def _download_weights(self):
        target=WEIGHTS_DIR/'megaloc'
        target.mkdir(parents=True,exist_ok=True)
        before=folder_size(target)
        log=LOG_DIR/'megaloc.log'
        cmd=[sys.executable,'-c',
             'import sys; from huggingface_hub import hf_hub_download; hf_hub_download(repo_id="gberton/MegaLoc",filename="model.safetensors",local_dir=sys.argv[1])',str(target)]
        # Hugging Face Hub/Xet need a writable home in the persistent models volume.
        cache=MODEL_CACHE_DIR
        locations={
            'HOME':cache,
            'XDG_CACHE_HOME':cache/'xdg',
            'HF_HOME':cache/'huggingface',
            'HF_HUB_CACHE':cache/'huggingface'/'hub',
            'HF_XET_CACHE':cache/'huggingface'/'xet',
            'TORCH_HOME':cache/'torch',
        }
        for folder in locations.values():
            folder.mkdir(parents=True,exist_ok=True)
        env=os.environ.copy()
        env.update({key:str(path) for key,path in locations.items()})
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
