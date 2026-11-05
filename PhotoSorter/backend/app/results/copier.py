"""Create safe, collision-free result entries without altering original photos."""
from pathlib import Path
import hashlib
from ..photos.labels import check_label
from server.storage.hardlinks import link_or_copy

def copy_photo(source,model_dir,label,expected_stamp=None):
    source=Path(source)
    if not source.is_file(): raise FileNotFoundError(source)
    name=check_label(label) if label!='_Неопределено' else label
    directory=Path(model_dir)/name
    if directory.is_symlink():
        raise ValueError('Symlink output directory forbidden')
    directory.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(str(source.resolve()).encode('utf-8')).hexdigest()[:12]
    basename=f'{digest}_{source.name}'
    for i in range(100000):
        dest=directory/(basename if i==0 else f'{digest}_{i}_{source.name}')
        try:
            link_or_copy(source,dest,expected_stamp=expected_stamp)
            return dest
        except FileExistsError: continue
    raise RuntimeError('Слишком много совпадений имён файлов')
