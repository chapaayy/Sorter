"""Explicit route/action map. No prefix-based privilege inheritance."""
import re
import uuid
from fastapi import HTTPException
from .roles import has,level

U=r"[0-9a-fA-F-]{36}"
R=r"[0-9]{8}T[0-9]{6}-[a-f0-9]{12}"
RULES=[]
def add(method,path,key,obj=None):
    RULES.append((method,re.compile("/api/"+path),key,obj))

add("GET","batches","photos.view")
add("POST","batches","photos.create")
for suffix,key in (("","view"),("/runs","view"),("/retention","view"),("/deletion","view"),("/media/errors","view"),("/photos","media"),("/gallery","media"),("/pending","upload"),("/upload-manifest","upload")):
    add("GET",f"batches/({U})"+suffix,"photos."+key,"batch")
for method,suffix,key in (("PATCH","","rename"),("DELETE","","delete"),("DELETE",f"/photos/{U}","delete_file"),("PUT","/upload-manifest","upload"),("POST","/media/retry","prepare"),("POST","/auto-processing/cancel","auto"),("POST","/downloads/confirm","retention"),("POST","/retention/extend","retention")):
    add(method,f"batches/({U})"+suffix,"photos."+key,"batch")
add("POST","uploads","photos.upload")
add("PUT",f"uploads/direct/{U}","photos.upload")
for method,suffix in (("GET",""),("PATCH",""),("DELETE",""),("POST","/finish")):
    add(method,f"uploads/({U})"+suffix,"photos.upload","upload")
for suffix,key in (("preview","media"),("prepared","media"),("original","download")):
    add("GET",f"photos/({U})/"+suffix,"photos."+key,"media")
add("GET",f"thumbnails/({U})","photos.media","media")
add("GET",f"thumbnails/status/({U})/counts","photos.media","batch")
add("POST",f"thumbnails/({U})/retry","photos.prepare","upload")
add("GET","runs","queue.view")
add("POST","runs","photos.enqueue")
add("GET",f"runs/({R})","queue.detail","run")
add("POST",f"runs/({R})/stop","queue.stop","run")
add("GET","work-queue","queue.view")
add("GET","work-queue/own-status","queue.view")
add("GET",f"reference-preparations/{U}","queue.shared")
add("POST",f"reference-preparations/{U}/(?:retry|skip|stop)","queue.preparation")
add("GET",f"logs/({R})(?:/page)?","logs.view","run")
add("GET","logs/usage","logs.usage")
add("GET","logs/runs","logs.view")
for method,path,key in (
    ("GET",r"references(?:/files|/cache/status|/[^/]+/photos)?","view"),
    ("GET","references/export","export"),("POST","references/constructions","create"),
    ("PATCH","references/constructions/[^/]+(?:/address)?","edit"),("PATCH","references/[^/]+/sides","sides"),
    ("DELETE","references/files/[^/]+","delete_file"),("DELETE","references/sam/[^/]+","delete"),
    ("POST","references/import/preview","import"),("GET","regions","view"),("POST","regions","region"),
    ("GET","reference-library/(?:status|events)","view"),("POST","reference-library/notices/ack","view"),
    ("GET",rf"reference-imports(?:/{U}(?:/files/{U})?)?","import"),
    ("POST",rf"reference-imports(?:/(?:portable-preview|portable-catalog|resolve-sides|compare)|/{U}/(?:complete|files/{U}/(?:finish|duplicate)))?","import"),
    ("PUT",rf"reference-imports/{U}/manifest","import"),("PATCH",rf"reference-imports/{U}/files/{U}","import")):
    add(method,path,"references."+key)
for method,path,key in (
    ("GET","storage/usage","view"),("GET","storage/(?:breakdown|operations)","diagnostics"),
    ("GET","storage/(?:accounting/issues|inventory/files|host-audit(?:/live)?)","diagnostics"),
    ("GET","storage/(?:inventory/report.csv|host-audit/(?:report.csv|write-sites.csv|report.json|live-events.jsonl))","report"),
    ("POST","storage/(?:reconcile|independent-check|inventory/scan)","check"),
    ("GET","storage/limits","limits"),("PATCH","storage/limits","configure"),
    ("GET","storage/(?:maintenance|maintenance/[^/]+/preview|host-maintenance/[^/]+/preview)","maintenance"),
    ("POST","storage/(?:maintenance|host-maintenance)/[^/]+","maintenance")):
    add(method,path,"storage."+key)
for method,path,key in (
    ("GET","system/status","status"),("GET","models","models"),("POST","models/megaloc/download","download_model"),
    ("GET","processing-settings","processing_view"),("PATCH","processing-settings","processing"),
    ("GET","processing-settings/(?:cpu|workloads)","performance_view"),("PATCH","processing-settings/(?:cpu|workloads)","performance"),
    ("GET","system/retention","retention_view"),("PATCH","system/retention","retention"),
    ("GET","system/update","update_status"),("POST","system/update/(?:check|start)","update")):
    add(method,path,"system."+key)
for method,path,key in (
    ("GET","admin/accounts","view"),("GET","admin/accounts/roles","roles"),("GET","admin/accounts/registration","requests"),
    ("PUT","admin/accounts/registration","registration"),("GET","admin/accounts/events","history"),
    ("GET",r"admin/accounts/[0-9]+","view"),("POST",r"admin/accounts/[0-9]+/security","security"),
    ("GET",r"admin/access-requests","requests"),("GET",r"storage/accounts(?:/[0-9]+)?","storage"),
    ("GET","admin/users","view"),("POST","admin/users","create"),
    ("PUT",r"admin/accounts/[0-9]+","edit_account"),
    ("POST","admin/accounts/roles","role_edit"),("PUT","admin/accounts/roles/[^/]+","role_edit"),
    ("POST","admin/accounts/roles/[^/]+/delete","role_delete"),
    ("POST",rf"admin/access-requests/{U}/decision","approve"),
    ("GET",rf"admin/access-requests/{U}/grants","grants"),("PUT",rf"admin/access-requests/{U}/grants","grants"),
    ("GET",r"admin/users/[0-9]+/grants","grants"),("PUT",r"admin/users/[0-9]+/grants","grants"),
    ("PATCH",r"storage/accounts/[0-9]+/limit","quota"),
    ("GET",r"admin/accounts/[0-9]+/lifecycle","view"),("POST",r"admin/accounts/[0-9]+/lifecycle","lifecycle")):
    add(method,path,"accounts."+key)

def resolve(method,path):
    method="GET" if method=="HEAD" else method
    for verb,pattern,key,obj in RULES:
        match=pattern.fullmatch(path)
        if verb==method and match:return key,obj,match.group(1) if obj else None
    return None

def require(user,key):
    if not has(user,key):raise HTTPException(403,"Недостаточно прав")
    from .roles import CATALOG
    dependency=CATALOG.get(key,{}).get("requires")
    if dependency:
        require(user,dependency)
    if key in ('queue.shared','queue.preparation'):
        require(user,'queue.view')
        if key=='queue.preparation':require(user,'queue.shared')

def owner_filter(user,key):
    if not user or (user.get("username")=="admin" and user.get("access_role")=="owner"):return None
    require(user,key)
    return None if level(user,key)=="all" else user["id"]

def batch_access(db,user,batch_id,key,*,lock=False):
    if not user:return
    require(user,key)
    try:identifier=uuid.UUID(str(batch_id))
    except (ValueError,TypeError):raise HTTPException(404,"Фотоотчёт не найден")
    row=db.execute("SELECT owner_id,delete_state FROM batches WHERE id=%s"+(" FOR SHARE" if lock else ""),(identifier,)).fetchone()
    if row is None:raise HTTPException(404,"Фотоотчёт не найден")
    if user.get("username")=="admin" and user.get("access_role")=="owner":
        if row["delete_state"]=="transferring":raise HTTPException(409,"Фотоотчёт передаётся")
        return
    for action in ({key,"photos.view"} if key.startswith("photos.") else {key,"queue.view"} if key.startswith("queue.") else {key}):
        scope=level(user,action)
        if scope!="all" and not(scope=="own" and row["owner_id"]==user["id"]):
            raise HTTPException(404,"Фотоотчёт не найден")
    if row["delete_state"]=="transferring":raise HTTPException(409,"Фотоотчёт передаётся")

def authorize_object(user,key,obj,identifier):
    from ..database import connect
    if not obj:return
    with connect() as db:
        if obj=="batch":return batch_access(db,user,identifier,key)
        if obj=="run":
            row=db.execute("SELECT batch_id FROM jobs WHERE id=%s",(identifier,)).fetchone()
        else:
            try:uid=uuid.UUID(identifier)
            except ValueError:raise HTTPException(404,"Объект не найден")
            row=db.execute("SELECT batch_id,kind FROM uploads WHERE id=%s",(uid,)).fetchone()
            if row and row["kind"]=="reference" and obj=="media":
                require(user,"references.view")
                if key=="photos.download":require(user,"references.download")
                return
            if row and row["kind"]!="fo":row=None
        if not row or not row["batch_id"]:raise HTTPException(404,"Объект не найден")
        batch_access(db,user,row["batch_id"],key)

def authorize_route(user,method,path):
    rule=resolve(method,path)
    if rule is None:raise HTTPException(403,"Недостаточно прав")
    key,obj,identifier=rule
    if key=="accounts.security":
        if not any(has(user,k) for k in ("accounts.block","accounts.password","accounts.revoke")):
            raise HTTPException(403,"Недостаточно прав")
    elif key=="photos.enqueue":
        if not any(has(user,k) for k in ("photos.process","photos.reprocess")):raise HTTPException(403,"Недостаточно прав")
    elif key=="accounts.lifecycle":
        if not any(has(user,k) for k in ("accounts.transfer","accounts.delete")):raise HTTPException(403,"Недостаточно прав")
    elif key=="accounts.edit_account":
        if not any(has(user,k) for k in ("accounts.edit","accounts.assign","accounts.overrides")):raise HTTPException(403,"Недостаточно прав")
    elif obj=="media":
        if not has(user,key) and not has(user,"references.view"):raise HTTPException(403,"Недостаточно прав")
    elif method in ('GET','HEAD') and path=='/api/regions':
        if not any(has(user,k) for k in ('references.view','photos.process','photos.reprocess','photos.auto')):raise HTTPException(403,'Недостаточно прав')
    else:require(user,key)
    if method=="POST" and path=="/api/reference-imports/portable-catalog":require(user,"references.create")
    if method=="POST" and path=="/api/reference-imports/resolve-sides":require(user,"references.sides")
    authorize_object(user,key,obj,identifier)
    return key
