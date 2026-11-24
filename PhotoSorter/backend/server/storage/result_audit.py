"""Bounded verification of expected media from canonical manifests.

No duplicated result index, content hashing, or deletion. Only discrepancies
are retained. A crashed audit restarts from the immutable manifest.
"""
import json,os,stat,time,uuid
from app.results.exporter import MANIFEST_NAME
from app.storage.categories import Category
from app.storage.paths import app_key,relative_media_key
from app.storage.filesystem import safe_read
from .registry import stat_key

MAX_ROW=1024*1024

class ResultAudit:
    def __init__(self):
        self.cursor=""
        self.run=None
        self.offset=0
        self.index=0
        self.stamp=None
        self.generation=None

    def _reset(self):
        self.offset=0
        self.index=0
        self.stamp=None
        self.generation=uuid.uuid4()

    def _done(self):
        self.cursor=self.run
        self.run=None

    def _issues(self,db,issues):
        if not issues:return
        with db.cursor() as cur:
            cur.executemany("""INSERT INTO storage_result_issues(path,run_id,issue,generation)
              VALUES(%s,%s,%s,%s) ON CONFLICT(path) DO UPDATE SET issue=excluded.issue,
              generation=excluded.generation,observed_at=clock_timestamp()""",
              [(path,self.run,reason,self.generation) for path,reason in issues])

    def step(self,db,root,limit=256):
        # Lock the selected job only for this bounded transaction. Deletion
        # can proceed between ticks; the FK removes its diagnostic rows.
        query="""SELECT j.id,j.batch_id,b.owner_id,j.snapshot->'models'->'megaloc' AS model
          FROM jobs j JOIN batches b ON b.id=j.batch_id
          WHERE b.delete_state='active' AND j.snapshot->'models'->'megaloc'->>'status'='completed'"""
        if self.run is None:
            row=db.execute(query+" AND j.id>%s ORDER BY j.id LIMIT 1 FOR KEY SHARE OF j",(self.cursor,)).fetchone()
            if not row:return True
            self.run=row["id"]
            self._reset()
        else:
            row=db.execute(query+" AND j.id=%s FOR KEY SHARE OF j",(self.run,)).fetchone()
            if not row:self._done();return False
        fields={"user_id":row["owner_id"],"batch_uuid":row["batch_id"],"run_id":self.run}
        try:
            manifest=app_key(Category.RESULT_METADATA,**fields).relative/MANIFEST_NAME
            media=app_key(Category.RESULT_MEDIA,**fields).relative
        except ValueError:
            self._done()
            return False
        manifest_key="app/"+manifest.as_posix()
        found=[]
        complete=False
        invalid=False
        try:
            with safe_read(root,manifest) as stream:
                st=os.fstat(stream.fileno())
                stamp=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
                if self.stamp is not None and stamp!=self.stamp:self._reset()
                self.stamp=stamp
                stream.seek(self.offset)
                deadline=time.monotonic()+.25
                for _ in range(limit):
                    if time.monotonic()>=deadline:break
                    line=stream.readline(MAX_ROW+1)
                    if not line:
                        expected=row["model"].get("processed")
                        complete=expected is None or expected==self.index
                        invalid=not complete
                        break
                    if len(line)>MAX_ROW:invalid=True;break
                    try:
                        item=json.loads(line)
                        if item["index"]!=self.index:raise ValueError("Wrong manifest index")
                        key="app/"+(media/relative_media_key(item["copy"])).as_posix()
                        key.encode("utf-8")
                    except (ValueError,KeyError,TypeError,UnicodeError):
                        invalid=True;break
                    try:
                        if not stat.S_ISREG(stat_key(root,key).st_mode):found.append((key,"invalid_result_media"))
                    except (FileNotFoundError,NotADirectoryError):
                        found.append((key,"missing_result_media"))
                    except OSError:
                        found.append((key,"unreadable_result_media"))
                    self.offset=stream.tell()
                    self.index+=1
                # An out-of-band replacement/in-place write is not a coherent
                # manifest scan. Retry this run next tick without clearing old evidence.
                end=os.fstat(stream.fileno())
                if stamp!=(end.st_dev,end.st_ino,end.st_size,end.st_mtime_ns,end.st_ctime_ns):
                    self._reset()
                    return False
        except FileNotFoundError:
            # Canonical manifest absence is already reported by missing_keys.
            self._done()
            return False
        except (OSError,ValueError):
            invalid=True
        if invalid:found.append((manifest_key,"invalid_result_manifest"))
        self._issues(db,found)
        if complete and not invalid:
            db.execute("DELETE FROM storage_result_issues WHERE run_id=%s AND generation<>%s",(self.run,self.generation))
        if complete or invalid:self._done()
        return False
