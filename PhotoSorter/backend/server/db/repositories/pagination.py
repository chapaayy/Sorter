"""Opaque deterministic cursor for database keyset pagination, no offsets in new galleries."""
from __future__ import annotations
import base64,json,uuid
from datetime import datetime
from fastapi import HTTPException

def encode(at,photo_id):
    obj={"at":at.isoformat(),"id":str(photo_id)}
    return base64.urlsafe_b64encode(json.dumps(obj,separators=(",",":")).encode()).decode().rstrip("=")

def decode(cursor):
    if not cursor:return None
    try:
        if len(cursor)>512:raise ValueError("oversized cursor")
        value=json.loads(base64.urlsafe_b64decode(cursor+"="*(-len(cursor)%4)))
        at=datetime.fromisoformat(value["at"])
        if at.tzinfo is None:raise ValueError("cursor must be timezone aware")
        return at,uuid.UUID(value["id"])
    except (ValueError,TypeError,KeyError,UnicodeDecodeError,OverflowError) as exc:
        raise HTTPException(422,"Неверный курсор") from exc

def page(db,filter_sql,params,*,cursor=None,limit=60):
    """Call with fixed trusted SQL predicates, never user-provided SQL."""
    if not 1<=limit<=200:raise HTTPException(422,"Неверный лимит")
    seek=decode(cursor)
    extra=" AND (u.created_at,u.id)>(%s,%s)" if seek else ""
    rows=db.execute(f"""SELECT u.id,u.filename,u.checksum,u.declared_size,u.created_at,
        u.kind,u.batch_id,u.sam,u.finalized,
        t.state AS thumbnail_status,t.last_error AS thumbnail_error
      FROM uploads u LEFT JOIN thumbnail_tasks t ON t.upload_id=u.id
      WHERE {filter_sql}{extra}
      ORDER BY u.created_at,u.id LIMIT %s""",
      (*params,*(seek or ()),limit+1)).fetchall()
    next_cursor=encode(rows[limit-1]["created_at"],rows[limit-1]["id"]) if len(rows)>limit else None
    results=[]
    for row in rows[:limit]:
        results.append({"id":str(row["id"]),"name":row["filename"],
           "bytes":row["declared_size"],"created_at":row["created_at"],
           "thumbnail_status":row["thumbnail_status"] or "pending",
           "thumbnail_url":f'/api/thumbnails/{row["id"]}' if row["finalized"] else None})
    return {"photos":results,"next_cursor":next_cursor}
