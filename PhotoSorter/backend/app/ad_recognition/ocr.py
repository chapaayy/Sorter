"""Optional PaddleOCR PP-OCRv5 East-Slavic CPU check, never a classifier."""
from __future__ import annotations
import hashlib
import json
import os
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

def _digest(path:Path)->str:
    hash=hashlib.sha256()
    with path.open("rb") as stream:
        while chunk:=stream.read(1024*1024):hash.update(chunk)
    return hash.hexdigest()

def _manifest():
    files={}
    for name in (DETECTION,RECOGNITION):
        folder=ROOT/name
        if not _ready(folder):raise RuntimeError("Missing PP-OCRv5 model "+name)
        for file in sorted(folder.rglob("*")):
            if file.is_symlink():raise RuntimeError("Unsafe OCR symlink")
            if file.is_file():
                files[file.relative_to(ROOT).as_posix()]=_digest(file)
    if not files:raise RuntimeError("Empty PP-OCRv5 model files")
    return {"version":VERSION,"files":files}

def _verify():
    if ROOT.is_symlink() or not all(_ready(ROOT/name) for name in (DETECTION,RECOGNITION)):
        return False
    try:
        stored=json.loads((ROOT/"manifest.json").read_text("utf-8"))
        if stored.get("version")!=VERSION:return False
        files=stored.get("files")
        if not isinstance(files,dict) or not files:return False
        for name,digest in files.items():
            rel=Path(name)
            if (rel.is_absolute() or ".." in rel.parts or
                rel.parts[0] not in (DETECTION,RECOGNITION) or
                not (ROOT/rel).is_file() or (ROOT/rel).is_symlink() or
                _digest(ROOT/rel)!=digest):
                return False
        return set(files)==set(_manifest()["files"])
    except (ValueError,OSError,TypeError,KeyError,IndexError):
        return False

def status():
    return {"available":_verify(),
            "version":VERSION,"detection":DETECTION,"recognition":RECOGNITION}

def signature()->str:
    """A run pins exact downloaded Paddle checkpoint hashes, not only model names."""
    if not _verify():
        raise RuntimeError("Не установлены проверенные PP-OCRv5 модели")
    return hashlib.sha256(VERSION.encode()+b":"+(ROOT/"manifest.json").read_bytes()).hexdigest()

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
    if status()["available"]:return status()
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
    manifest=_manifest()
    temp=ROOT/".manifest.tmp"
    try:
        temp.write_text(json.dumps(manifest,sort_keys=True),encoding="utf-8")
        os.replace(temp,ROOT/"manifest.json")
    finally:
        temp.unlink(missing_ok=True)
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
        polygons=obj.get("rec_polys")
        for index,(text,score) in enumerate(zip(obj.get("rec_texts",[]),obj.get("rec_scores",[]))):
            score=float(score)
            if isinstance(text,str) and score>=.5 and len(text.strip())>=2:
                line={"text":text.strip()[:200],"score":round(score,3)}
                if polygons is not None and index<len(polygons):
                    coords=np.asarray(polygons[index],dtype="float64")
                    if (coords.size>=6 and coords.size<=32 and coords.size%2==0
                            and np.isfinite(coords).all()):
                        line["polygon"]=coords.reshape(-1,2).round(1).tolist()
                lines.append(line)
    return lines[:50]

def _norm(text:str)->str:
    return " ".join(re.findall(r"[a-zа-яё0-9]+",text.casefold()))

def _critical(text:str)->dict:
    """OCR-visible numeric/date/price tokens; no language-model guessing."""
    # Keep punctuation until numeric structures have been extracted.
    value=text.casefold().replace("ё","е")
    dates=set()
    for hit in re.finditer(r"(?<!\d)(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?(?!\d)",value):
        day,month,year=hit.groups()
        if 1<=int(day)<=31 and 1<=int(month)<=12:
            dates.add(f"{int(day):02}.{int(month):02}"+(f".{year}" if year else ""))
    months=("январ","феврал","март","апрел","мая","июн","июл",
            "август","сентябр","октябр","ноябр","декабр")
    for m in re.finditer(r"(?<!\\d)(\\d{1,2})\\s+([а-яё]+)(?:\\s+(20\\d{2}))?",value):
        day,word,year=m.groups()
        month=next((i+1 for i,stem in enumerate(months) if word.startswith(stem)),None)
        if month and 1<=int(day)<=31:
            dates.add(f"{int(day):02}.{month:02}"+(f".{year}" if year else ""))
    percent={m.group(1).replace(",",".") for m in re.finditer(
        r"(?<!\w)(\d+(?:[.,]\d+)?)\s*%",value)}
    prices={m.group(1).replace(",",".") for m in re.finditer(
        r"(?<!\w)(\d+(?:[.,]\d+)?)\s*(?:₽|руб(?:лей|ля|\.)?|р\.)",value)}
    numbers={m.group().replace(",",".") for m in re.finditer(
        r"(?<![\w])\d+(?:[.,]\d+)?(?![\w])",value)}
    # Dates and percentages are also represented among bare numbers.
    return {"dates":sorted(dates),"percentages":sorted(percent),
            "prices":sorted(prices),"numbers":sorted(numbers)}


def describe(observed:list[dict])->dict:
    """Preserve OCR evidence independently from any DINO candidate/layout."""
    lines=[]
    for item in observed[:50]:
        text=item.get("text")
        try:score=float(item.get("score",0))
        except (ValueError,TypeError):continue
        if not isinstance(text,str) or not text.strip() or not np.isfinite(score):
            continue
        line={"text":text.strip()[:200],"score":round(min(1.,max(0.,score)),3)}
        polygon=item.get("polygon")
        if isinstance(polygon,list) and 3<=len(polygon)<=16:
            try:
                coords=np.asarray(polygon,dtype="float64")
                if coords.shape==(len(polygon),2) and np.isfinite(coords).all():
                    line["polygon"]=coords.round(1).tolist()
            except (TypeError,ValueError):
                pass
        lines.append(line)
    usable=[item for item in lines if item["score"]>=.5]
    content=" ".join(item["text"] for item in usable)
    confidence=round(float(np.average(
        [line["score"] for line in usable],
        weights=[max(1,len(line["text"])) for line in usable])),3) if usable else 0.
    return {"status":"readable" if usable else "unreadable",
            "raw_lines":lines,"normalized_text":_norm(content),
            "confidence":confidence,"significant":_critical(content),
            "regions":[{"text":item["text"],"score":item["score"],
                        "polygon":item["polygon"]}
                       for item in usable if "polygon" in item]}


def confirm(expected_text:str,observed:list[dict])->dict:
    """OCR only verifies or flags the DINO candidate; never selects a layout.

    A readable different date, percent or price contradicts the layout even
    when generic shared slogan words appear in both images. A missing value,
    poor OCR or weak lexical overlap is NOT a positive contradiction.
    """
    data=describe(observed)
    expected=_norm(expected_text or "")
    actual=data["normalized_text"]
    texts=[item["text"] for item in data["raw_lines"] if item["score"]>=.5]
    base={**data,"lines":texts,"expected_text":expected,
          "contradictions":[],"matched_terms":0,"total_terms":0}
    if not expected:
        return {**base,"status":"not_configured",
                "reason":"Текст исходного макета отсутствует"}
    if not actual:
        return {**base,"status":"unreadable",
                "reason":"Текст на экране не прочитан; это не противоречие"}
    expected_significant=_critical(expected_text or "")
    observed_significant=data["significant"]
    contradictions=[]
    for category in ("dates","prices","percentages"):
        left=set(expected_significant[category])
        right=set(observed_significant[category])
        if left and right and not (left & right):
            contradictions.append({"kind":category,
                                   "expected":sorted(left),"observed":sorted(right)})
    # An unsuffixed number matters when both images have readable numbers:
    # e.g. the same 'скидка' slogan with 40 instead of 50.
    left=set(expected_significant["numbers"])
    right=set(observed_significant["numbers"])
    if left and right and not left.issubset(right) and not contradictions:
        # Avoid treating unrelated extra numbers (different OCR layouts)
        # as definitive when they still share at least one control number.
        if not (left & right):
            contradictions.append({"kind":"numbers",
                                   "expected":sorted(left),"observed":sorted(right)})
    terms=[word for word in expected.split() if len(word)>=3 or word.isdigit()]
    if not terms:terms=expected.split()
    hits=sum(1 for term in terms if any(
        SequenceMatcher(None,term,word).ratio()>=.82 for word in actual.split()))
    ratio=hits/max(1,len(terms))
    base.update(matched_terms=hits,total_terms=len(terms),
                text_similarity=round(ratio,3),contradictions=contradictions)
    if contradictions:
        return {**base,"status":"mismatch",
                "reason":"Читаемые числа, дата или цена противоречат макету"}
    if ratio>=.6 and data["confidence"]>=.70 and (not left or left.issubset(right)):
        return {**base,"status":"confirmed",
                "reason":"Читаемый текст согласуется с макетом"}
    if (hits==0 and len(expected.split())>=2 and len(actual.split())>=1
            and data["confidence"]>=.85):
        return {**base,"status":"mismatch",
                "reason":"Высокоуверенный читаемый текст не совпадает с макетом"}
    return {**base,"status":"probable",
            "reason":"Недостаточно надёжных текстовых совпадений для подтверждения или опровержения"}
