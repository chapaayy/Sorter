"""Optional PaddleOCR PP-OCRv5 East-Slavic CPU check, never a classifier."""
from __future__ import annotations
import re
from difflib import SequenceMatcher
from pathlib import Path
import numpy as np
from PIL import Image
from app.config import WEIGHTS_DIR,MODEL_CACHE_DIR

DETECTION="PP-OCRv5_mobile_det"
RECOGNITION="eslav_PP-OCRv5_mobile_rec"
ROOT=WEIGHTS_DIR/"paddleocr"
CACHE=MODEL_CACHE_DIR/"paddlex"
VERSION="PP-OCRv5-eslav-cpu-v1"

def _ready(path:Path):
    if not path.is_dir() or path.is_symlink():return False
    return any(f.is_file() and not f.is_symlink() and f.stat().st_size>100000
               for f in path.iterdir()) and (
        (path/"inference.yml").is_file() or (path/"model.yml").is_file())

def status():
    return {"available":_ready(ROOT/DETECTION) and _ready(ROOT/RECOGNITION),
            "version":VERSION,"detection":DETECTION,"recognition":RECOGNITION}

def _init(det_dir:Path|None,rec_dir:Path|None):
    from paddleocr import PaddleOCR
    return PaddleOCR(
        ocr_version="PP-OCRv5",lang="ru",device="cpu",
        text_detection_model_name=DETECTION,
        text_recognition_model_name=RECOGNITION,
        text_detection_model_dir=str(det_dir) if det_dir else None,
        text_recognition_model_dir=str(rec_dir) if rec_dir else None,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,use_textline_orientation=False)

def install():
    """Explicit API command downloads both model folders, then pins local copies."""
    import shutil
    import os
    os.environ["PADDLE_PDX_CACHE_HOME"]=str(CACHE)
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE","bos")
    # Constructors download inference files through PaddleX when not present.
    pipeline=_init(None,None)
    del pipeline
    source=CACHE/"official_models"
    for name in (DETECTION,RECOGNITION):
        src=source/name
        if not _ready(src):
            raise RuntimeError("PaddleOCR could not provision "+name)
        dest=ROOT/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not _ready(dest):
            shutil.copytree(src,dest,dirs_exist_ok=True)
    return status()

def load():
    if not status()["available"]:
        raise RuntimeError("PaddleOCR PP-OCRv5 ru not installed. Run --install-ocr in API.")
    return _init(ROOT/DETECTION,ROOT/RECOGNITION)

def read(engine,picture:Image.Image)->list[dict]:
    """PaddleOCR 3.x's public JSON result fields; ignore unreliable text."""
    array=np.ascontiguousarray(np.asarray(picture.convert("RGB")))
    results=engine.predict(array)
    lines=[]
    for item in results:
        obj=item.json
        obj=obj.get("res",obj)
        for text,score in zip(obj.get("rec_texts",[]),obj.get("rec_scores",[])):
            score=float(score)
            if isinstance(text,str) and score>=.5 and len(text.strip())>=2:
                lines.append({"text":text.strip()[:200],"score":round(score,3)})
    return lines[:50]

def _norm(text:str)->str:
    return " ".join(re.findall(r"[a-zа-яё0-9]+",text.casefold()))

def confirm(expected_text:str,observed:list[dict])->dict:
    expected=_norm(expected_text)
    texts=[item["text"] for item in observed if item.get("score",0)>=.5]
    actual=_norm(" ".join(texts))
    if not expected:
        return {"status":"not_configured","reason":"Для макета не указан контрольный текст","lines":texts}
    if not actual:
        return {"status":"unreadable","reason":"Не удалось прочитать текст на ФО","lines":[]}
    terms=[word for word in expected.split() if len(word)>=3]
    if not terms:
        terms=expected.split()
    hits=sum(1 for term in terms if any(SequenceMatcher(None,term,word).ratio()>=.82
                                      for word in actual.split()))
    ratio=hits/max(1,len(terms))
    return {"status":"confirmed" if ratio>=.6 else "mismatch",
            "reason":"Контрольный текст совпадает" if ratio>=.6 else "Контрольный текст не совпал",
            "matched_terms":hits,"total_terms":len(terms),
            "lines":texts}
