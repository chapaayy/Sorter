"""Recoverable transfer/deletion using canonical batch paths and the registry.

A committed plan records each source inode before any rename. A retry accepts
only the exact recorded inode at source OR destination, never overwrites a
destination. Source accounts and batches stay blocked until DB publication.
Personal files are never removed by generic recursive deletion.
"""
from pathlib import Path
import os,stat
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from app import config
from app.storage.filesystem import parent_fd,safe_unlink
from ..database import connect
from ..storage import admission,registry,thumbnail_cache
from ..storage.paths import batch_root,owned_directory,owned_file
from . import accounts,cleanup
from .account_activity import lease
from .account_move import move, fingerprint as _fingerprint, rewrite as _rewrite, _stat

ACTIVE=("queued","running","retry")

def _lock(db):
    # Scheduling before admission, matching upload finalization.
    db.execute("SELECT pg_advisory_xact_lock(723409133)")
    admission.lock(db)

def _busy(db,owner):
    return db.execute("""SELECT EXISTS(
      SELECT 1 FROM batch_operations o JOIN batches b ON b.id=o.batch_id WHERE b.owner_id=%s
      UNION ALL SELECT 1 FROM jobs j JOIN batches b ON b.id=j.batch_id WHERE b.owner_id=%s AND j.status IN ('queued','running','stopping')
      UNION ALL SELECT 1 FROM work_queue w JOIN batches b ON b.id=w.media_batch_id WHERE b.owner_id=%s AND w.state IN ('queued','running','blocked')
      UNION ALL SELECT 1 FROM thumbnail_tasks t JOIN uploads u ON u.id=t.upload_id JOIN batches b ON b.id=u.batch_id WHERE b.owner_id=%s AND t.state='running'
      UNION ALL SELECT 1 FROM storage_reservations WHERE owner_id=%s
      UNION ALL SELECT 1 FROM uploads u JOIN batches b ON b.id=u.batch_id WHERE b.owner_id=%s AND NOT u.finalized
      UNION ALL SELECT 1 FROM batches WHERE owner_id=%s AND auto_process_state='waiting' AND delete_state='active'
      ) AS busy""",(owner,)*7).fetchone()["busy"]

def preview(owner):
    with connect() as db:
        row=db.execute("SELECT id,username FROM users WHERE id=%s",(owner,)).fetchone()
        if not row:raise HTTPException(404,"Аккаунт не найден")
        count=db.execute("SELECT count(*) AS n FROM batches WHERE owner_id=%s AND delete_state<>'deleted'",(owner,)).fetchone()["n"]
        usage=admission.account_budget(db,owner)
        state=db.execute("SELECT operation,state,detail,recipient_id,requested_at,finished_at FROM account_lifecycle WHERE source_id=%s",(owner,)).fetchone()
        return {"username":row["username"],"batches":count,"quota":usage,"active_operations":_busy(db,owner),"operation":state}

def request(actor,source,operation,recipient,confirmation):
    if confirmation is None:raise HTTPException(422,"Подтвердите логин аккаунта")
    with connect() as db:
        _lock(db)
        acting=accounts.authority(db,actor,"accounts.delete" if operation!="transfer" else "accounts.transfer")
        if operation=="transfer_delete":accounts.require(acting,"accounts.transfer")
        if not accounts.is_owner(acting):
            from ..security.roles import level
            needed="photos.delete" if operation=="delete" else "photos.view"
            if level(acting,needed)!="all":raise HTTPException(403,"Недостаточно прав на данные")
        source_row=accounts.target(db,source,acting)
        if confirmation!=source_row["username"]:raise HTTPException(422,"Логин подтверждения не совпадает")
        if db.execute("""SELECT 1 FROM account_lifecycle WHERE state<>'completed' AND
          (source_id=ANY(%s) OR recipient_id=ANY(%s)) LIMIT 1""",([source,recipient] if recipient else [source],)*2).fetchone():
            raise HTTPException(409,"Для аккаунта уже выполняется операция")
        if operation!="delete":
            if recipient is None or recipient==source:raise HTTPException(422,"Выберите другой аккаунт")
            # Owner may receive data, but delegated admins may not target owner.
            target=db.execute("SELECT id,username,access_role,role_id,blocked,permission_overrides FROM users WHERE id=%s FOR UPDATE",(recipient,)).fetchone()
            if not target or target["blocked"]:raise HTTPException(422,"Получатель недоступен")
            accounts.check_target(db,acting,target)
            if _busy(db,source) or _busy(db,recipient):raise HTTPException(409,"Завершите загрузки, подготовку и обработку фотоотчётов перед передачей")
            source_budget=admission.account_budget(db,source)
            recipient_budget=admission.account_budget(db,recipient)
            if recipient_budget["enabled"] and recipient_budget["available_bytes"]<source_budget["used_bytes"]:raise HTTPException(409,"Недостаточно личной квоты получателя")
            if db.execute("SELECT 1 FROM batches WHERE owner_id=%s AND delete_state NOT IN ('active','deleted') LIMIT 1",(source,)).fetchone():
                raise HTTPException(409,"Дождитесь завершения удаления фотоотчётов")
        elif recipient is not None:raise HTTPException(422,"Для удаления получатель не нужен")
        db.execute("""INSERT INTO account_lifecycle(source_id,recipient_id,operation,state,actor,was_blocked)
          VALUES (%s,%s,%s,'queued',%s,%s) ON CONFLICT(source_id) DO UPDATE SET
          recipient_id=excluded.recipient_id,operation=excluded.operation,state='queued',actor=excluded.actor,
          was_blocked=excluded.was_blocked,plan=NULL,detail=NULL,requested_at=now(),next_attempt=now(),finished_at=NULL""",
          (source,recipient,operation,actor,source_row["blocked"]))
        db.execute("UPDATE users SET blocked=true WHERE id=%s",(source,))
        db.execute("DELETE FROM sessions WHERE user_id=%s",(source,))
        if operation!="delete":
            db.execute("UPDATE batches SET delete_state='transferring' WHERE owner_id=%s AND delete_state='active'",(source,))
        accounts.audit(db,actor,source,"account_lifecycle_requested",{"operation":operation,"recipient":recipient})
    return {"state":"queued"}

def _move(root,entry):
    move(root,entry,parent_fd,owned_directory)

def _owner_root(owner):
    # The canonical batch and thumbnail contract share this owner prefix.
    from app.storage.paths import managed_prefix
    from app.storage.categories import Category
    return managed_prefix(Category.FO_THUMBNAIL,user_id=owner,version=thumbnail_cache.VERSION).parent.parent

def _files(root):
    if not root.exists():return
    if root.is_symlink():raise ValueError("Символьная ссылка вместо каталога аккаунта")
    device=root.stat().st_dev
    def failed(exc):raise exc
    for folder,dirs,files in os.walk(root,followlinks=False,onerror=failed):
        for name in dirs:
            p=Path(folder)/name;st=p.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_dev!=device:raise ValueError("Небезопасный каталог аккаунта")
        for name in files:
            p=Path(folder)/name;st=p.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_dev!=device:raise ValueError("Неизвестный объект в данных аккаунта")
            yield p,st

def _make_plan(db,source,recipient):
    if _busy(db,source):raise ValueError("Ожидаем завершения активных операций")
    if not admission._ready(db):raise ValueError("Ожидаем актуального учёта")
    root=Path(config.APP_STORAGE_ROOT)
    old=owned_directory(_owner_root(source),root);new=owned_directory(_owner_root(recipient),root)
    old_prefix="app/"+old.relative_to(root).as_posix()+"/"
    rows=db.execute("SELECT path,category,owner_id,scope,issue,device,inode,allocated_bytes,logical_bytes,batch_id FROM storage_files WHERE starts_with(path,%s)",(old_prefix,)).fetchall()
    evidence={r["path"]:r for r in rows}
    moves=[];keys=[];seen=set();charge=0
    from collections import Counter
    observed=Counter();links={}
    batches={r["id"] for r in db.execute("SELECT id FROM batches WHERE owner_id=%s AND delete_state='transferring'",(source,))}
    for batch in batches:
        src=batch_root(batch,source);dst=batch_root(batch,recipient)
        st=_stat(src)
        if st is not None:
            if not stat.S_ISDIR(st.st_mode) or _stat(dst) is not None:raise ValueError("Конфликт пути фотоотчёта")
            moves.append({"src":src.relative_to(root).as_posix(),"dst":dst.relative_to(root).as_posix(),"inode":_fingerprint(st),"kind":"directory"})
    for p,st in _files(old):
        key="app/"+p.relative_to(root).as_posix();r=evidence.pop(key,None)
        if not r or r["scope"]!="personal" or r["owner_id"]!=source or r["issue"] or (r["device"],int(r["inode"]),r["allocated_bytes"],r["logical_bytes"])!=(st.st_dev,st.st_ino,st.st_blocks*512,st.st_size):
            raise ValueError("Ожидаем сверки всех личных файлов или устранения неизвестных объектов")
        inode=(st.st_dev,st.st_ino)
        observed[inode]+=1;links[inode]=st.st_nlink
        dest=new/p.relative_to(old)
        if r["category"]=="fo_thumbnail":
            expected=thumbnail_cache.location(p.stem,owner_id=source)
            if expected!=p:raise ValueError("Неизвестный путь миниатюры")
            other=_stat(dest)
            if other is not None:
                if not stat.S_ISREG(other.st_mode):raise ValueError("Конфликт миниатюры получателя")
                # Reuse its existing preview. Source remains until normal GC.
                continue
            moves.append({"src":p.relative_to(root).as_posix(),"dst":dest.relative_to(root).as_posix(),"inode":_fingerprint(st),"kind":"file"})
        elif r["batch_id"] not in batches or not p.is_relative_to(batch_root(r["batch_id"],source)):
            raise ValueError("Файл не принадлежит передаваемому фотоотчёту")
        inode=(st.st_dev,st.st_ino)
        if inode not in seen:
            seen.add(inode);charge+=max(st.st_size,st.st_blocks*512)
        keys.extend([key,"app/"+dest.relative_to(root).as_posix()])
    if any(observed[inode]!=count for inode,count in links.items()):raise ValueError('Обнаружены hardlink за пределами данных аккаунта')
    if evidence:raise ValueError("Реестр содержит ещё не сверенные пути аккаунта")
    if db.execute("SELECT 1 FROM storage_result_issues i JOIN jobs j ON j.id=i.run_id JOIN batches b ON b.id=j.batch_id WHERE b.owner_id=%s LIMIT 1",(source,)).fetchone():raise ValueError("Обнаружены расхождения результатов; передача остановлена")
    # All business originals and normalized files must actually exist.
    for row in db.execute("""SELECT target_path,media_output_path FROM uploads u JOIN batches b ON b.id=u.batch_id
        WHERE b.owner_id=%s AND b.delete_state='transferring' AND u.finalized""",(source,)):
        for path in (row["target_path"],row["media_output_path"]):
            if path is not None:
                owned_file(Path(path),old)
                if not Path(path).is_file():raise ValueError("Не найден исходный файл")
    return {"moves":moves,"keys":keys,"charge":charge,"batches":[str(v) for v in sorted(batches)]}

def _quota(db,recipient,charge):
    row=db.execute("SELECT blocked FROM users WHERE id=%s FOR UPDATE",(recipient,)).fetchone()
    if not row or row["blocked"]:raise ValueError("Получатель недоступен")
    budget=admission.account_budget(db,recipient)
    if budget["enabled"] and budget["available_bytes"]<charge:raise ValueError("Недостаточно личной квоты получателя")

def _transfer(row):
    source,recipient=row["source_id"],row["recipient_id"]
    root=Path(config.APP_STORAGE_ROOT)
    # Commit the journal before the first irreversible rename. Even a process
    # kill between rename and DB commit can replay exact inode identities.
    with connect() as db:
        _lock(db)
        current=db.execute("SELECT * FROM account_lifecycle WHERE source_id=%s FOR UPDATE",(source,)).fetchone()
        if not current or current["state"]=="completed":return
        plan=current["plan"]
        if plan is None:
            if _busy(db,recipient):raise ValueError('Ожидаем завершения активных операций получателя')
            plan=_make_plan(db,source,recipient);_quota(db,recipient,plan["charge"])
            db.execute("UPDATE account_lifecycle SET plan=%s,state='running',detail=NULL WHERE source_id=%s",(Jsonb(plan),source))
    with connect() as db:
        _lock(db)
        current=db.execute("SELECT * FROM account_lifecycle WHERE source_id=%s FOR UPDATE",(source,)).fetchone()
        plan=current["plan"]
        _quota(db,recipient,plan["charge"])
        if _busy(db,source) or _busy(db,recipient):raise ValueError("Ожидаем завершения активных операций")
        old=str(_owner_root(source));new=str(_owner_root(recipient))
        for entry in plan["moves"]:_move(root,entry)
        # Update only canonical path prefixes; manifests store relative keys.
        for batch in plan["batches"]:
            from uuid import UUID
            bid=UUID(batch)
            for upload in db.execute("SELECT id,target_path,media_output_path FROM uploads WHERE batch_id=%s",(bid,)):
                db.execute("UPDATE uploads SET target_path=%s,media_output_path=%s WHERE id=%s",
                    (_rewrite(upload["target_path"],old,new),_rewrite(upload["media_output_path"],old,new),upload["id"]))
            for job in db.execute("SELECT id,snapshot FROM jobs WHERE batch_id=%s",(bid,)):
                db.execute("UPDATE jobs SET snapshot=%s WHERE id=%s",(Jsonb(_rewrite(job["snapshot"],old,new)),job["id"]))
            if not db.execute("UPDATE batches SET owner_id=%s,delete_state='active' WHERE id=%s AND owner_id=%s AND delete_state='transferring' RETURNING id",(recipient,bid,source)).fetchone():raise ValueError("Состояние фотоотчёта изменилось")
            db.execute("UPDATE storage_files SET owner_id=%s WHERE batch_id=%s AND scope<>'personal'",(recipient,bid))
            db.execute("DELETE FROM storage_result_issues WHERE run_id IN (SELECT id FROM jobs WHERE batch_id=%s)",(bid,))
            for task in db.execute("SELECT t.upload_id,t.checksum,t.version FROM thumbnail_tasks t JOIN uploads u ON u.id=t.upload_id WHERE u.batch_id=%s AND t.state='ready'",(bid,)):
                if not thumbnail_cache.location(task["checksum"],task["version"],owner_id=recipient).is_file():
                    db.execute("UPDATE thumbnail_tasks SET state='queued',attempts=0,lease_until=NULL WHERE upload_id=%s",(task["upload_id"],))
        # Refresh the one registry transactionally, not a second byte ledger.
        for start in range(0,len(plan["keys"]),512):registry.observe(db,root,plan["keys"][start:start+512],onerror=lambda:(_ for _ in ()).throw(ValueError("Ошибка учёта после передачи")))
        db.execute("UPDATE storage_accounting_state SET requested_at=now()")
        if row["operation"]=="transfer_delete":
            db.execute("UPDATE account_lifecycle SET operation='delete',recipient_id=NULL,plan=NULL,state='queued',detail=NULL,next_attempt=now() WHERE source_id=%s",(source,))
        else:
            db.execute("UPDATE users SET blocked=%s WHERE id=%s",(row["was_blocked"],source))
            db.execute("UPDATE account_lifecycle SET state='completed',plan=NULL,detail=NULL,finished_at=now() WHERE source_id=%s",(source,))
        from ..storage.accounting import refresh
        refresh(db,force=True)
        accounts.audit(db,row["actor"],source,"account_data_transferred",{"recipient":recipient,"batches":len(plan["batches"])})

def _delete(row):
    source=row["source_id"]
    with connect() as db:
        active=db.execute("SELECT id,delete_state FROM batches WHERE owner_id=%s AND delete_state<>'deleted'",(source,)).fetchall()
    for batch in active:
        if batch["delete_state"] in ("active","delete_failed"):cleanup.request(batch["id"])
    if active:return
    # All batch trees were removed by existing cleanup. Remove only canonical
    # derived owner previews, never shared or unknown files.
    with connect() as db:
        _lock(db)
        if _busy(db,source):return
        root=Path(config.APP_STORAGE_ROOT)
        own=owned_directory(_owner_root(source),root)
        keys=[]
        files=list(_files(own))
        for p,st in files:
            if p!=thumbnail_cache.location(p.stem,owner_id=source):
                raise ValueError("Остались неизвестные личные файлы; аккаунт не удалён")
        for p,st in files:
            safe_unlink(root,p.relative_to(root),missing_ok=True)
            keys.append(registry.key_for(p))
        if keys:registry.observe(db,root,keys)
        # Do not remove owner metadata while the registry still has evidence.
        if db.execute("SELECT 1 FROM storage_files WHERE owner_id=%s LIMIT 1",(source,)).fetchone():
            db.execute("UPDATE storage_accounting_state SET requested_at=now()")
            return
        user=db.execute("SELECT username FROM users WHERE id=%s FOR UPDATE",(source,)).fetchone()
        if not user:return
        db.execute("DELETE FROM batches WHERE owner_id=%s AND delete_state='deleted'",(source,))
        db.execute("DELETE FROM access_requests WHERE email=%s",(user["username"],))
        db.execute("DELETE FROM users WHERE id=%s AND username<>'admin'",(source,))
        accounts.audit(db,row["actor"],source,"account_deleted")
        db.execute("DELETE FROM account_lifecycle WHERE source_id=%s",(source,))

def run_pending():
    # Reuse existing cleanup thread and never wait behind a long upload.
    with connect() as db:
        row=db.execute("SELECT * FROM account_lifecycle WHERE state<>'completed' AND next_attempt<=now() ORDER BY next_attempt LIMIT 1").fetchone()
    if not row:return
    with lease(exclusive=True) as allowed:
        if not allowed:return
        try:
            if row["operation"]=="delete":_delete(row)
            else:_transfer(row)
        except Exception as exc:
            # No rollback of a successful rename is guessed. The journal
            # preserves evidence; retry is idempotent and fails closed.
            with connect() as db:
                db.execute("UPDATE account_lifecycle SET state='retry',detail=%s,next_attempt=now()+interval '60 seconds' WHERE source_id=%s",
                    (str(exc)[:500],row["source_id"]))
        else:
            with connect() as db:
                db.execute("UPDATE account_lifecycle SET next_attempt=now()+interval '5 seconds' WHERE source_id=%s AND state<>'completed'",(row["source_id"],))
