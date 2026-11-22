"""Translate internal MegaLoc paths into portable, human-readable ZIP names."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

from . import archives
from ..storage.paths import owned_directory,owned_file,run_dir
from .construction_catalog import construction_title

_FORBIDDEN=re.compile(r'[<>:"/\\|?*]')
_DEVICES=re.compile(r'^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|(?:COM|LPT)[1-9¹²³])$',re.I)
_MAX_UNITS=240
_MAX_BYTES=250


def _truncate(value,units,bytes_limit):
    value=value.encode("utf-16-le")[:2*units].decode("utf-16-le","ignore")
    return value.encode("utf-8")[:bytes_limit].decode("utf-8","ignore")


def portable_name(value,fallback,*,file=False):
    name=_FORBIDDEN.sub("_","".join(
        "_" if unicodedata.category(c) in ("Cc","Cs") else c for c in value))
    name=name.strip().rstrip(". ") or fallback
    return _with_suffix(name,"",file=file)


def _with_suffix(name,suffix,*,file):
    original_extension=Path(name).suffix if file else ""
    # Keep the actual image extension; limit it for unusual legacy names.
    extension=_truncate(original_extension,24,80)
    stem=name[:-len(original_extension)] if original_extension else name
    tail=suffix+extension
    result=(_truncate(stem,_MAX_UNITS-len(tail.encode("utf-16-le"))//2,
                      _MAX_BYTES-len(tail.encode("utf-8"))).rstrip(". ") or "_")+tail
    return "_"+result if _DEVICES.fullmatch(result.split(".",1)[0].rstrip(" ")) else result


def _key(value):
    return unicodedata.normalize("NFC",value).casefold()


def _unique(names,*,file=False):
    # Keep genuine names such as IMG (2).JPG even if IMG.JPG repeats.
    reserved={_key(name) for name in names}
    used=set()
    counters=defaultdict(lambda:2)
    for name in names:
        key=_key(name)
        candidate=name
        if key in used:
            while True:
                number=counters[key]
                counters[key]+=1
                candidate=_with_suffix(name,f" ({number})",file=file)
                if _key(candidate) not in reserved and _key(candidate) not in used:
                    break
        used.add(_key(candidate))
        yield candidate


@dataclass(frozen=True)
class ArchivePlan:
    title:str
    files:list[tuple[Path,str]]


def build(db,run_id,batch_id,title,rows,sam=None):
    report=db.execute("""SELECT CASE WHEN b.report_date_mode='manual' THEN b.report_date
        ELSE (COALESCE(j.started_at,j.created_at) AT TIME ZONE 'Europe/Samara')::date
        END AS archive_date FROM jobs j JOIN batches b ON b.id=j.batch_id
        WHERE j.id=%s AND b.id=%s""",(run_id,batch_id)).fetchone()
    if not report or report['archive_date'] is None:
        raise ValueError('Дата фотоотчёта не найдена')
    folder_date=report['archive_date'].isoformat()
    filtered=[row for row in rows if sam is None or row["assigned_sam"]==sam]
    labels=list(dict.fromkeys(row["assigned_sam"] for row in filtered))
    constructions=db.execute("""SELECT sam,kind,address FROM reference_constructions
        WHERE sam=ANY(%s)""",(labels,)).fetchall()
    names={r["sam"]:construction_title(r["sam"],r["kind"],r["address"]) for r in constructions}
    directories=dict(zip(labels,_unique([portable_name(names.get(label,label),"Конструкция")
                                        for label in labels])))
    paths=list({row["query"] for row in filtered if row.get("query")})
    uploads=db.execute("""SELECT DISTINCT ON (target_path) target_path,filename FROM uploads
        WHERE batch_id=%s AND kind='fo' AND finalized AND target_path=ANY(%s)
        ORDER BY target_path,created_at,id""",(batch_id,paths)).fetchall()
    originals={row["target_path"]:row["filename"] for row in uploads}
    root=portable_name(title,"Фотоотчёт")
    run=owned_directory(run_dir(run_id,archives.output_root()),archives.output_root())
    outputs=owned_directory(run/"megaloc",run)
    groups=defaultdict(list)
    for row in filtered:
        source=owned_file(Path(row['copy']),outputs)
        if not source.is_file():
            raise FileNotFoundError('Отсутствует готовый файл: '+source.name)
        query=row.get('query')
        name=row.get('export_name') or originals.get(query) or Path(query or source.name).name
        kind='video' if row.get('media_kind')=='video' else 'image'
        side=row.get('side')
        side_folder=portable_name('Сторона '+side,'Неназначена сторона') if side else 'Неназначена сторона'
        groups[(kind,row['assigned_sam'],side_folder)].append((source,portable_name(name,'Фото'+source.suffix,file=True)))
    files=[]
    for (kind,label,side_folder),media in groups.items():
        directory=root+'/'+('Видео/' if kind=='video' else '')+archives.archive_member(directories[label],folder_date,side_folder)
        for (source,_),name in zip(media,_unique([name for _,name in media],file=True)):
            files.append((source,directory+'/'+name))
    return ArchivePlan(root,files)
