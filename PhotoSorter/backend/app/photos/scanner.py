"""Scan and validate incoming photo reports; reference inputs are pinned SQL snapshots."""
from pathlib import Path
from .reader import EXTS
from PIL import Image

def images(folder):
    folder=Path(folder).expanduser().resolve()
    if not folder.is_dir(): raise ValueError(f'Папка не найдена: {folder}')
    return sorted((p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in EXTS),key=lambda p:str(p).casefold())

def validate(paths,progress=None,should_stop=None,warn=None):
    good=[]; errors={}
    for i,path in enumerate(paths,1):
        if should_stop and should_stop(): raise InterruptedError('Остановлено')
        try:
            # Header/integrity check only: avoid fully decoding every photo
            # twice. MegaLoc's decoder catches corrupt image payloads later.
            with Image.open(path) as image:
                image.verify()
            good.append(path)
        except (OSError, ValueError, TypeError) as exc:
            reason=f'{type(exc).__name__}: {exc}'
            errors[str(path)]=reason
            if warn: warn(f'Повреждённое изображение {path.name}: {reason}')
        if progress: progress(i,len(paths),path.name)
    return good,errors

