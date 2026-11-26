"""Account management on the existing users, sessions, grants and quota tables.

All mutations in this module are owner-only at the router and serialized.
The protected account is never a mutation target. No filesystem mutation here.
"""
import secrets
from uuid import uuid4
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from ..database import connect
from ..auth import hash_password
from ..security.access_policy import is_owner
from ..security.roles import CATALOG,validate,effective,delegable,has
from ..security.route_permissions import require
from ..storage import admission

def lock(db):
    db.execute("SELECT pg_advisory_xact_lock(723409192)")

def audit(db,actor,target,action,detail=None):
    db.execute("INSERT INTO account_admin_events(actor,target,action,detail) VALUES (%s,%s,%s,%s)",
               (actor,str(target),action,Jsonb(detail or {})))
    db.execute("DELETE FROM account_admin_events WHERE id IN (SELECT id FROM account_admin_events ORDER BY id DESC OFFSET 2000)")

def authority(db,actor,key=None):
    # Resolve again under the account/admission transaction lock: a stale
    # request snapshot cannot continue to grant rights after revocation.
    row=db.execute("""SELECT u.id,u.username,u.access_role,u.role_id,u.blocked,
        u.permission_overrides,r.permissions AS role_permissions FROM users u
        JOIN account_roles r ON r.id=u.role_id WHERE u.username=%s""",(actor,)).fetchone()
    if not row or row["blocked"]:raise HTTPException(403,"Недостаточно прав")
    row["permissions"]=effective(row["role_permissions"],row["permission_overrides"])
    if key:require(row,key)
    return row

def check_desired(actor,permissions):
    if not is_owner(actor) and not delegable(actor,permissions):
        raise HTTPException(403,"Нельзя выдать или изменить полномочия выше своего уровня")

def check_target(db,actor,row):
    if is_owner(actor):return
    if actor["id"]==row["id"]:raise HTTPException(403,"Нельзя изменять собственные полномочия")
    if is_owner(row):raise HTTPException(403,"Аккаунт владельца защищён")
    permissions=effective(role(db,row["role_id"])["permissions"],row["permission_overrides"])
    check_desired(actor,permissions)
    if any(value!="none" and CATALOG[key].get("scoped") and actor["permissions"].get(key)!="all" for key,value in permissions.items()):
        raise HTTPException(403,"Недостаточно прав на данные управляемого аккаунта")
    # Explicit report grants are separate rights, not captured by role scopes.
    if db.execute("SELECT 1 FROM result_access_grants WHERE user_id=%s LIMIT 1",(row["id"],)).fetchone():
        if not all(has(actor,k) and actor["permissions"].get(k)=="all" for k in ("results.view","results.media","results.zip")):
            raise HTTPException(403,"Аккаунт имеет отдельные права на результаты")

def target(db,user_id,actor=None):
    row=db.execute("SELECT id,username,access_role,role_id,blocked,permission_overrides FROM users WHERE id=%s FOR UPDATE",(user_id,)).fetchone()
    if not row:raise HTTPException(404,"Аккаунт не найден")
    if is_owner(row):raise HTTPException(403,"Аккаунт владельца защищён")
    if db.execute("SELECT 1 FROM account_lifecycle WHERE state<>'completed' AND (source_id=%s OR recipient_id=%s) LIMIT 1",(user_id,user_id)).fetchone():raise HTTPException(409,"Выполняется операция с аккаунтом")
    if actor is not None:check_target(db,actor,row)
    return row

def role(db,role_id):
    row=db.execute("SELECT * FROM account_roles WHERE id=%s",(role_id,)).fetchone()
    if not row or role_id=="owner":raise HTTPException(422,"Недопустимая роль")
    return row

def roles():
    with connect() as db:
        rows=db.execute("""SELECT r.*, (SELECT count(*) FROM users u WHERE u.role_id=r.id) AS users
                          FROM account_roles r ORDER BY r.id""").fetchall()
    return {"items":rows,"catalog":CATALOG}

def save_role(actor,role_id,name,description,permissions):
    permissions=validate(permissions)
    if not name or '\x00' in name or '\x00' in description:raise HTTPException(422,'Некорректное название или описание')
    with connect() as db:
        lock(db)
        acting=authority(db,actor,"accounts.role_edit")
        check_desired(acting,effective(permissions,{}))
        if role_id=="owner":raise HTTPException(403,"Роль владельца защищена")
        if role_id is not None:
            old=role(db,role_id)
            check_desired(acting,effective(old["permissions"],{}))
            for row in db.execute("SELECT id,username,access_role,role_id,permission_overrides FROM users WHERE role_id=%s FOR UPDATE",(role_id,)):
                check_target(db,acting,row)
                check_desired(acting,effective(permissions,row["permission_overrides"]))
        if db.execute("SELECT 1 FROM account_roles WHERE lower(name)=lower(%s) AND id IS DISTINCT FROM %s",(name,role_id)).fetchone():
            raise HTTPException(409,"Роль с таким названием уже существует")
        identifier=role_id or uuid4().hex
        db.execute("""INSERT INTO account_roles(id,name,description,permissions) VALUES (%s,%s,%s,%s)
          ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description,permissions=excluded.permissions""",
          (identifier,name,description,Jsonb(permissions)))
        audit(db,actor,identifier,"role_updated" if role_id else "role_created",{"name":name,"permissions":permissions})
        return {"id":identifier}

def delete_role(actor,role_id,replacement):
    if role_id in ("owner","observer","administrator","employee"):
        raise HTTPException(403,"Начальную роль можно редактировать, но нельзя удалить")
    with connect() as db:
        lock(db);acting=authority(db,actor,"accounts.role_delete");old=role(db,role_id)
        check_desired(acting,effective(old["permissions"],{}))
        count=db.execute("SELECT count(*) AS n FROM users WHERE role_id=%s",(role_id,)).fetchone()["n"]
        if count:
            if not replacement or replacement==role_id:raise HTTPException(409,"Выберите другую роль для пользователей")
            require(acting,"accounts.assign")
            new=role(db,replacement)
            for row in db.execute("SELECT id,username,access_role,role_id,permission_overrides FROM users WHERE role_id=%s FOR UPDATE",(role_id,)):
                check_target(db,acting,row)
                check_desired(acting,effective(new["permissions"],row["permission_overrides"]))
            db.execute("UPDATE users SET role_id=%s WHERE role_id=%s",(replacement,role_id))
        db.execute("DELETE FROM account_roles WHERE id=%s",(role_id,))
        audit(db,actor,role_id,"role_deleted",{"replacement":replacement,"users":count})
    return {"ok":True}

def list_accounts(search,limit,offset,*,include_storage=True):
    from ..storage.accounting import snapshot
    data=snapshot()
    with connect() as db:
        stats=db.execute("SELECT count(*) AS total,count(*) FILTER(WHERE NOT blocked) AS active,count(*) FILTER(WHERE blocked) AS blocked FROM users").fetchone()
        query="WHERE position(lower(%s) in lower(u.username||' '||u.display_name))>0 OR %s=''"
        rows=db.execute("""SELECT u.id,u.username,u.display_name,u.role_id,u.blocked,u.created_at,u.last_login_at,
          u.storage_limit_bytes,r.name AS role_name FROM users u JOIN account_roles r ON r.id=u.role_id """+query+
          " ORDER BY u.id LIMIT %s OFFSET %s",(search,search,limit+1,offset)).fetchall()
        if not include_storage:
            for row in rows:row.pop("storage_limit_bytes",None)
            return {"items":rows[:limit],"has_more":len(rows)>limit,"stats":stats,"sampled_at":None,"partial":True}
        values=admission.counters(db);settings=admission.policy(db)
        for row in rows:
            row["usage"]=data.get("owners",{}).get(str(row["id"]),{"allocated_bytes":0} if data.get("sampled_at") and not data.get("partial") else None)
            row["quota"]=admission.account_budget(db,row["id"],values,settings)
    return {"items":rows[:limit],"has_more":len(rows)>limit,"stats":stats,"sampled_at":data.get("sampled_at"),"partial":data.get("partial",True)}

def detail(user_id,*,include_sessions=True):
    with connect() as db:
        row=db.execute("""SELECT u.id,u.username,u.display_name,u.role_id,u.blocked,u.created_at,u.last_login_at,
            u.permission_overrides,r.permissions AS role_permissions,r.name AS role_name
            FROM users u JOIN account_roles r ON r.id=u.role_id WHERE u.id=%s""",(user_id,)).fetchone()
        if not row:raise HTTPException(404,"Аккаунт не найден")
        row["permissions"]=effective(row["role_permissions"],row["permission_overrides"])
        row["sessions"]=db.execute("""SELECT session_id,created_at,expires_at FROM sessions
            WHERE user_id=%s AND expires_at>now() ORDER BY expires_at DESC""",(user_id,)).fetchall() if include_sessions else []
    return row

def configure_new(db,user_id,role_id,display_name,limit,overrides,*,acting=None):
    chosen=role(db,role_id)
    overrides=validate(overrides)
    if acting is not None:
        require(acting,"accounts.assign")
        if overrides:require(acting,"accounts.overrides")
        if limit is not None:require(acting,"accounts.quota")
        check_desired(acting,effective(chosen["permissions"],overrides))
    from ..services import disk_guard
    from app import config
    if '\x00' in display_name:raise HTTPException(422,'Некорректное имя')
    if limit is not None:
        total,_=disk_guard.stat(config.APP_STORAGE_ROOT)
        if not 0<=limit<=total:raise HTTPException(422,'Лимит должен быть в пределах ёмкости диска')
    db.execute('UPDATE users SET role_id=%s,display_name=%s,permission_overrides=%s,storage_limit_bytes=%s WHERE id=%s',
               (role_id,display_name,Jsonb(overrides),limit,user_id))

def edit(actor,user_id,name,role_id,overrides):
    overrides=validate(overrides)
    if '\x00' in name:raise HTTPException(422,'Некорректное имя')
    with connect() as db:
        lock(db);acting=authority(db,actor);old=target(db,user_id,acting);chosen=role(db,role_id)
        current=db.execute("SELECT display_name FROM users WHERE id=%s",(user_id,)).fetchone()["display_name"]
        if name!=current:require(acting,"accounts.edit")
        if role_id!=old["role_id"]:require(acting,"accounts.assign")
        if overrides!=old["permission_overrides"]:require(acting,"accounts.overrides")
        check_desired(acting,effective(chosen["permissions"],overrides))
        db.execute("UPDATE users SET display_name=%s,role_id=%s,permission_overrides=%s WHERE id=%s",
                   (name,role_id,Jsonb(overrides),user_id))
        audit(db,actor,user_id,"account_updated",{"role":role_id,"previous_role":old["role_id"],"overrides":overrides})
    return detail(user_id,include_sessions=has(acting,"accounts.sessions"))

def security(actor,user_id,action,password=None,session_id=None):
    # Serialize with login's row lock. A login before blocking is revoked,
    # and a login after blocking cannot create a session.
    with connect() as db:
        lock(db)
        key={"block":"accounts.block","unblock":"accounts.block","reset_password":"accounts.password","revoke_all":"accounts.revoke","revoke_session":"accounts.revoke"}.get(action)
        if key is None:raise HTTPException(422,"Неизвестное действие")
        acting=authority(db,actor,key);target(db,user_id,acting)
        if action in ("block","unblock"):
            db.execute("UPDATE users SET blocked=%s WHERE id=%s",(action=="block",user_id))
            if action=="block":db.execute("DELETE FROM sessions WHERE user_id=%s",(user_id,))
        elif action=="reset_password":
            if not isinstance(password,str) or not 12<=len(password)<=256 or "\x00" in password:
                raise HTTPException(422,"Пароль должен содержать от 12 до 256 символов")
            salt=secrets.token_bytes(16)
            db.execute("UPDATE users SET password_salt=%s,password_hash=%s WHERE id=%s",(salt.hex(),hash_password(password,salt),user_id))
            db.execute("DELETE FROM sessions WHERE user_id=%s",(user_id,))
        elif action=="revoke_all":db.execute("DELETE FROM sessions WHERE user_id=%s",(user_id,))
        elif action=="revoke_session":
            if not session_id:raise HTTPException(422,"Выберите сессию")
            db.execute("DELETE FROM sessions WHERE user_id=%s AND session_id=%s",(user_id,session_id))
        else:raise HTTPException(422,"Неизвестное действие")
        audit(db,actor,user_id,action)
    return {"ok":True}

def registration(enabled=None,actor=None):
    with connect() as db:
        if enabled is not None:
            lock(db);authority(db,actor,"accounts.registration")
            db.execute("UPDATE account_registration SET enabled=%s",(enabled,))
            audit(db,actor,"registration","registration_changed",{"enabled":enabled})
        row=db.execute("SELECT enabled FROM account_registration").fetchone()
        row["pending"]=db.execute("SELECT count(*) AS n FROM access_requests WHERE status='pending'").fetchone()["n"]
    return row

def events(offset):
    with connect() as db:
        return {"items":db.execute("SELECT * FROM account_admin_events ORDER BY id DESC LIMIT 50 OFFSET %s",(offset,)).fetchall()}
