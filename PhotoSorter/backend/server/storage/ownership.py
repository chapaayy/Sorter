"""Authorization is independent of physical storage keys and viewer grants."""
from fastapi import HTTPException
from app.storage.paths import user_key
from ..security.access_policy import is_owner

def require_creator(db, owner_id):
    try:
        identifier = int(user_key(owner_id))
    except ValueError:
        raise HTTPException(403, "Недостаточно прав")
    row = db.execute("SELECT id,username,access_role FROM users WHERE id=%s FOR KEY SHARE",
                     (identifier,)).fetchone()
    if row is None or not is_owner(row):
        raise HTTPException(403, "Недостаточно прав")
    return identifier

def require_batch_owner(db, batch_id, owner_id):
    row = db.execute("SELECT owner_id FROM batches WHERE id=%s", (batch_id,)).fetchone()
    if row is None or str(row["owner_id"]) != user_key(owner_id):
        raise HTTPException(404, "Партия не найдена")
    return row["owner_id"]
