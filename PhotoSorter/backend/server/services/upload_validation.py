"""Validate portable basenames and classify saved FO without converting them."""
from pathlib import Path
import hashlib
import subprocess
import unicodedata

from fastapi import HTTPException
from PIL import Image
from PIL import UnidentifiedImageError
from app.photos.reader import EXTS
from ..storage.thumbnail_cache import PIXEL_LIMIT

MAX_FILE_BYTES=60*1024*1024
MAX_FO_BYTES=2*1024**3

def safe_name(value:str,*,reference:bool=False)->str:
    if (not value.strip() or value in ('.','..') or len(value)>200 or
        any(c in '<>:"/\\|?*' or unicodedata.category(c) in ('Cc','Cs') for c in value)):
        raise HTTPException(422,'Недопустимое имя файла: '+repr(value[:200]))
    if reference and Path(value).suffix.lower() not in EXTS:
        raise HTTPException(422,'Этот формат образца пока не поддерживается: '+repr(value))
    return value

def fo_media_type(path:Path,name:str)->str|None:
    """Null means a verified image supported by the existing MegaLoc scanner."""
    if Path(name).suffix.lower() in EXTS:
        try:
            with Image.open(path) as im:
                if im.width*im.height>PIXEL_LIMIT:
                    raise HTTPException(422,'Слишком большое разрешение изображения')
                im.verify()
        except UnidentifiedImageError:
            pass  # A media file may have the wrong extension.
        except (OSError,ValueError,Image.DecompressionBombError) as exc:
            raise HTTPException(422,'Файл не является корректным изображением: '+repr(name)) from exc
        else:
            return None
    # The argument is a server-generated .part path. Never use client MIME
    # as authority or decode/render an unsupported container on the server.
    try:
        result=subprocess.run(['file','--brief','--mime-type','--',str(path)],
                              capture_output=True,text=True,timeout=5,check=True)
    except (OSError,subprocess.SubprocessError) as exc:
        raise HTTPException(503,'Не удалось определить тип мультимедиа') from exc
    mime=result.stdout.strip()
    if not mime.startswith(('image/','video/')):
        if Path(name).suffix.lower() in EXTS:
            raise HTTPException(422,'Файл не является корректным изображением: '+repr(name))
        raise HTTPException(422,'Не удалось распознать фото или видео: '+repr(name))
    return mime

def original_storage_name(digest:str,name:str,media_type:str|None)->str:
    if media_type is not None:
        # This suffix is intentionally invisible to the existing photo scanner.
        return digest+'.media'
    suffix=Path(name).suffix
    # Reserve bytes for the digest prefixes added here and during export.
    encoded=Path(name).stem.encode('utf-8')
    stem=encoded.decode('utf-8')
    if len(encoded)>160:
        stem=encoded[:151].decode('utf-8','ignore')+'_'+hashlib.sha256(encoded).hexdigest()[:8]
    return f'{digest[:20]}_{stem}{suffix}'
