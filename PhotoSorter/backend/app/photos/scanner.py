"""Read SAM reference directories and unordered query photos."""
from pathlib import Path
from .reader import EXTS
from .labels import check_label
from PIL import Image

def images(folder):
    folder=Path(folder).expanduser().resolve()
    if not folder.is_dir(): raise ValueError(f'Папка не найдена: {folder}')
    return sorted((p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in EXTS),key=lambda p:str(p).casefold())

def references(folder, warn=None):
    root=Path(folder).expanduser().resolve()
    entries=[]; cache={}
    for file in images(root):
        parts=file.relative_to(root).parts
        if len(parts)<2: continue
        name=parts[0]
        if name not in cache:
            try: cache[name]=check_label(name)
            except ValueError as e:
                cache[name]=None
                if warn: warn(f'Пропуск папки {name}: {e}')
        if cache[name]: entries.append((file,cache[name]))
    if not entries: raise ValueError('Нет образцов в папках конструкций')
    return entries

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

def scan_folders(refs,queries,output):
    if not all(str(path).strip() for path in (refs,queries,output)):
        raise ValueError('Выбери все три папки')
    refs=Path(refs).expanduser().resolve(); queries=Path(queries).expanduser().resolve(); output=Path(output).expanduser().resolve()
    if refs==queries or refs in queries.parents or queries in refs.parents:
        raise ValueError('Образцы и новые фотографии должны быть в разных папках')
    for source in (refs,queries):
        if output==source or output in source.parents or source in output.parents:
            raise ValueError('Результаты должны быть вне исходных каталогов и образцов')
    item=references(refs)
    new=images(queries)
    if not new: raise ValueError('Нет новых фотографий')
    if output.exists() and not output.is_dir(): raise ValueError('Путь результатов не является папкой')
    # No output directory is created until a run starts.
    if not output.exists() and not output.parent.is_dir(): raise ValueError('Родительская папка результатов недоступна')
    return {'reference_count':len(item),'sam_count':len(set(label for _,label in item)),'new_count':len(new),'output_available':True}
