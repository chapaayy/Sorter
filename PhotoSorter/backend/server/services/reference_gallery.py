"""Gallery is a database projection of immutable shared objects."""
from __future__ import annotations
from ..storage.reference_objects import verify_object
from ..services import thumbnails

def index_published(db,item):
    target=verify_object(item["stored_path"],item["declared_size"],digest=item["checksum"])
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
