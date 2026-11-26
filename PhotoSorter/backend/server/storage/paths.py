"""Trusted batch/run paths; strict containment for existing storage callers."""
from pathlib import Path
import re
from dataclasses import dataclass
import stat
from app.config import DATA_DIR, RUNS_DIR
from app.storage.paths import uuid_key, run_key, managed_prefix, managed_path, relative_key, relative_media_key
from app.storage.categories import Category

RUN_PATTERN = re.compile(r"\d{8}T\d{6}-[a-f0-9]{12}\Z")

def batch_owner(batch_id, db=None):
    from ..database import connect
    batch_id=uuid_key(batch_id)
    if db is None:
        with connect() as conn:
            return batch_owner(batch_id,conn)
    row=db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch_id,)).fetchone()
    if not row:
        raise FileNotFoundError("Unknown batch")
    return row["owner_id"]

def batch_dir(batch_id, owner_id=None):
    owner_id=batch_owner(batch_id) if owner_id is None else owner_id
    return managed_prefix(Category.FO_ORIGINAL,user_id=owner_id,batch_uuid=batch_id)

def batch_root(batch_id, owner_id=None):
    return batch_dir(batch_id,owner_id).parent

def original_path(batch_id, upload_id, ext, owner_id=None):
    owner_id=batch_owner(batch_id) if owner_id is None else owner_id
    return managed_path(Category.FO_ORIGINAL,user_id=owner_id,batch_uuid=batch_id,upload_uuid=upload_id,ext=ext)

def normalized_path(batch_id, upload_id, ext, owner_id=None):
    owner_id=batch_owner(batch_id) if owner_id is None else owner_id
    return managed_path(Category.FO_NORMALIZED,user_id=owner_id,batch_uuid=batch_id,upload_uuid=upload_id,ext=ext)

def normalized_dir(batch_id, owner_id=None):
    owner_id=batch_owner(batch_id) if owner_id is None else owner_id
    return managed_prefix(Category.FO_NORMALIZED,user_id=owner_id,batch_uuid=batch_id)

def part_path(batch_id, upload_id):
    return managed_path(Category.FO_UPLOAD_PART,batch_uuid=batch_id,upload_uuid=upload_id)

def run_identity(run_id,db=None):
    from ..database import connect
    run_id=run_key(run_id)
    if db is None:
        with connect() as conn:
            return run_identity(run_id,conn)
    row=db.execute("""SELECT j.batch_id,b.owner_id FROM jobs j
        JOIN batches b ON b.id=j.batch_id WHERE j.id=%s AND b.delete_state<>'transferring'""",(run_id,)).fetchone()
    if not row:raise FileNotFoundError("Unknown run")
    return row["batch_id"],row["owner_id"]

def run_dir(run_id,*,db=None,identity=None):
    batch_id,owner_id=run_identity(run_id,db) if identity is None else identity
    return managed_path(Category.RESULT_MEDIA,user_id=owner_id,batch_uuid=batch_id,run_id=run_id).parent

def result_media_dir(run_id,*,db=None,identity=None):
    batch_id,owner_id=run_identity(run_id,db) if identity is None else identity
    return managed_path(Category.RESULT_MEDIA,user_id=owner_id,batch_uuid=batch_id,run_id=run_id)

def result_metadata_dir(run_id,*,db=None,identity=None):
    batch_id,owner_id=run_identity(run_id,db) if identity is None else identity
    return managed_path(Category.RESULT_METADATA,user_id=owner_id,batch_uuid=batch_id,run_id=run_id)


def _contained(path, root):
    root, candidate = Path(root), Path(path)
    if not root.is_absolute() or not candidate.is_absolute() or ".." in candidate.parts or ".." in root.parts:
        raise ValueError("File outside owned storage")
    if root.resolve() != root or not candidate.is_relative_to(root):
        raise ValueError("File outside owned storage")
    current = root
    # Reject all symlink components, even links resolving inside the root.
    for part in candidate.relative_to(root).parts:
        current = current / part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ValueError("Symlink inside owned storage")
        except FileNotFoundError:
            break
    return candidate

def owned_file(path, root):
    return _contained(path, root)

def owned_directory(path, root):
    return _contained(path, root)


@dataclass(frozen=True)
class ResultKeys:
    """Encode/decode canonical FO manifest paths at the Storage Manager boundary."""
    batch: Path
    originals: Path
    normalized: Path
    media: Path

    def source(self,path):
        path=Path(path)
        if path.is_relative_to(self.originals):return owned_file(path,self.originals)
        if path.is_relative_to(self.normalized):return owned_file(path,self.normalized)
        raise ValueError("File outside owned storage")

    def encode(self,row):
        row=dict(row)
        if row.get("query"):
            row["query"]=str(relative_key(self.source(row["query"]).relative_to(self.batch).as_posix()))
        row["copy"]=str(relative_media_key(owned_file(row["copy"],self.media).relative_to(self.media).as_posix()))
        return row

    def decode(self,row):
        row=dict(row)
        if row.get("query"):
            row["query"]=str(self.source(self.batch/relative_key(row["query"])))
        row["copy"]=str(owned_file(self.media/relative_media_key(row["copy"]),self.media))
        return row


def result_keys(run_id,*,identity=None):
    batch_id,owner_id=run_identity(run_id) if identity is None else identity
    return ResultKeys(batch_root(batch_id,owner_id),batch_dir(batch_id,owner_id),
                      normalized_dir(batch_id,owner_id),
                      result_media_dir(run_id,identity=(batch_id,owner_id)))
