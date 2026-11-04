"""Immutable source photos; create safe uniquely named copies per model/SAM."""
from pathlib import Path
import os,hashlib,shutil
from ..photos.labels import check_label

def copy_photo(source,model_dir,label,expected_stamp=None):
    source=Path(source).resolve()
    if not source.is_file(): raise FileNotFoundError(source)
    if expected_stamp is not None:
        stat=source.stat()
        if (stat.st_size,stat.st_mtime_ns)!=expected_stamp:
            raise ValueError(f'Фотография изменена после анализа: {source}')
    name=check_label(label) if label!='_Неопределено' else label
    directory=Path(model_dir)/name
    directory.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:12]
    basename=f'{digest}_{source.name}'
    # Exclusive-create never overwrites files already in an output directory.
    for i in range(100000):
        dest=directory/(basename if i==0 else f'{digest}_{i}_{source.name}')
        try:
            with open(dest,'xb') as out,open(source,'rb') as inp: shutil.copyfileobj(inp,out,1024*1024)
            shutil.copystat(source,dest)
            if expected_stamp is not None:
                stat=source.stat()
                if (stat.st_size,stat.st_mtime_ns)!=expected_stamp:
                    raise ValueError(f'Фотография изменена во время копирования: {source}')
            return dest
        except FileExistsError: continue
        except Exception:
            if dest.exists(): dest.unlink()
            raise
    raise RuntimeError('Слишком много совпадений имён файлов')
