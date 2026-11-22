"""Rename reference identities while retaining all historical immutable snapshots.

City, number, type and custom-name changes publish a new library version.
The original photos and reference embeddings are not modified.
"""
from __future__ import annotations

import json
from fastapi import HTTPException

from app.photos.labels import check_label
from ..database import connect
from ..db.repositories import reference_versions
from . import construction_catalog, reference_publication


def update(sam: str, kind: str, *, city_code=None, number=None,
           address=None, name=None) -> dict:
    try:
        if check_label(sam) != sam:
            raise ValueError("Недопустимый идентификатор конструкции")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    desired = construction_catalog.describe(
        kind, city_code=city_code, number=number, address=address, name=name
    )
    target = desired["sam"]
    with connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(723409133)")
        old = db.execute("""
            SELECT sam,kind,city_code,construction_number,address
            FROM reference_constructions WHERE sam=%s FOR UPDATE
        """, (sam,)).fetchone()
        if old is None:
            raise HTTPException(404, "Конструкция не найдена")
        if target != sam:
            # Do not rename identities during a queued or running MegaLoc /
            # reference-preparation task that might use the previous key.
            from .references import _idle
            _idle(db)
            if db.execute("""
                SELECT 1 FROM reference_constructions WHERE sam=%s
            """, (target,)).fetchone() or db.execute("""
                SELECT 1 FROM uploads WHERE kind='reference' AND sam=%s LIMIT 1
            """, (target,)).fetchone():
                raise HTTPException(409, "Конструкция с новым номером или названием уже существует")
            # An unfinished upload must not publish a reference with the old
            # identity after this transaction commits.
            if db.execute("""
                SELECT 1 FROM reference_import_files f
                JOIN reference_import_sessions s ON s.id=f.session_id
                WHERE f.sam IN (%s,%s) AND s.upload_state='uploading'
                LIMIT 1
            """, (sam,target)).fetchone():
                raise HTTPException(409, "Сначала завершите текущую загрузку образцов")
        elif old["kind"] != kind:
            raise HTTPException(422, "Укажите новое название при изменении типа")
        changed = any(
            old[field] != desired[field]
            for field in ("sam", "kind", "city_code", "construction_number", "address")
        )
        if not changed:
            return {**desired, "previous_sam":sam, "changed":False}
        version = reference_versions.current(db)
        if not version or version["id"] is None:
            raise HTTPException(409, "Библиотека ещё не инициализирована")
        db.execute("""
            UPDATE reference_constructions
            SET sam=%s,kind=%s,city_code=%s,construction_number=%s,
                address=%s,updated_at=now() WHERE sam=%s
        """, (target,kind,desired["city_code"],desired["construction_number"],
              desired["address"],sam))
        if target != sam:
            # Physical hardlinks stay under their old on-disk folder name.
            # The UUID, database gallery label and current version change.
            db.execute("""
                UPDATE uploads SET sam=%s WHERE kind='reference' AND sam=%s
            """, (target,sam))
            db.execute("UPDATE reference_photo_sides SET sam=%s WHERE sam=%s",(target,sam))
            members = [dict(item) for item in reference_versions.members(db,version["id"])]
            for item in members:
                if item["sam"] == sam:
                    item["sam"] = target
            new_version, published = reference_publication.publish(
                db,members,version["model_signature"],event_kind="reference_renamed"
            )
        else:
            new_version, published = version,False
        if not published:
            db.execute("""
                INSERT INTO reference_library_events(version_id,event_kind,details)
                VALUES (%s,%s,%s::jsonb)
            """, (version["id"],"reference_metadata_changed",
                  json.dumps({"previous_sam":sam,"sam":target,"kind":kind})))
    return {**desired,"previous_sam":sam,"changed":True,
            "version":new_version["version_number"]}
