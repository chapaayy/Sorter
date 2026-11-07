"""Published gallery index, separate from immutable recognition objects.

Gallery hardlinks are a read-only presentation of staged objects. A failed
transaction can leave an orphan link, but never a published half-version.
"""
from __future__ import annotations
import os
from pathlib import Path
from app.config import DATA_DIR
from app.photos.construction import parse_key
from ..storage.reference_objects import verify
from ..services import thumbnails

GALLERY=DATA_DIR/"references"

def index_published(db,item):
    target_dir=GALLERY/item["sam"]
    if GALLERY.is_symlink() or target_dir.is_symlink():
        raise ValueError("Unsafe reference gallery directory")
    target_dir.mkdir(parents=True,exist_ok=True)
    target=target_dir/(str(item["upload_id"])+"_"+item["filename"])
    if target.is_symlink():
        raise ValueError("Unsafe reference gallery file")
    source=Path(item["stored_path"])
    if not target.exists():
        try:
            os.link(source,target,follow_symlinks=False)
        except FileExistsError:
            pass
    verify(target,GALLERY,item["declared_size"],digest=item["checksum"])
    existing=db.execute("SELECT 1 FROM uploads WHERE id=%s",(item["upload_id"],)).fetchone()
    if existing:
        raise ValueError("Duplicate gallery file identifier")
    db.execute("""
        INSERT INTO uploads(id,kind,batch_id,sam,filename,declared_size,
            received,checksum,finalized,target_path)
        VALUES (%s,'reference',NULL,%s,%s,%s,%s,%s,true,%s)
    """,(item["upload_id"],item["sam"],item["filename"],item["declared_size"],
         item["declared_size"],item["checksum"],str(target)))
    thumbnails.enqueue(db,item["upload_id"],item["checksum"])
