"""Compact disposable end-to-end storage acceptance with real MegaLoc.

COCO validation images are diverse public test photographs, NOT outdoor
advertising ground truth. Videos are explicitly generated codec fixtures.
Never run against production. Report actual observations only.
"""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from urllib.parse import quote
import requests
import urllib3

ROOT=Path(__file__).resolve().parents[3]
STORAGE=ROOT/"storage"
BASE="https://localhost"
PASSWORD="stage10_disposable_password_only"
COUNT=10
VIDEO_COUNT=1
ZIP_TEST_REMAINING_SECONDS=60
CHUNK=16*1024**2
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def compose(*args,**kwargs):
    return subprocess.run(["docker","compose","--env-file",".env","--env-file",".env.generated",*args],cwd=ROOT,check=True,**kwargs)

def output(*args):
    return compose(*args,stdout=subprocess.PIPE,text=True).stdout.strip()

def client(username="admin",password=PASSWORD):
    s=requests.Session()
    s.verify=False
    s.headers["Origin"]=BASE
    req(s,"POST","/api/auth/login",json={"username":username,"password":password})
    return s

def req(s,method,path,**kwargs):
    resp=s.request(method,BASE+path,timeout=kwargs.pop("timeout",120),**kwargs)
    if not resp.ok:
        raise RuntimeError(f"{method} {path}: HTTP {resp.status_code}: {resp.text[:400]}")
    return resp

def obj(s,method,path,**kwargs):
    return req(s,method,path,**kwargs).json()

def wait(fn,*,timeout=900,period=2,description="condition"):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        val=fn()
        if val:return val
        time.sleep(period)
    raise TimeoutError(description)

def sql(query):
    return output("exec","-T","postgres","psql","-XAt","-v","ON_ERROR_STOP=1","-U","sorter","-d","sorter","-c",query)

def app_python(code):
    return output("exec","-T","api","python","-c",code)

def dataset(archive,folder):
    folder.mkdir()
    seen=set()
    paths=[]
    with zipfile.ZipFile(archive) as z:
        members=sorted((x for x in z.infolist() if re.fullmatch(r"val2017/\d{12}\.jpg",x.filename) and 0<x.file_size<20*1024**2),key=lambda x:x.filename)
        for m in members:
            data=z.read(m)
            digest=hashlib.sha256(data).hexdigest()
            if digest in seen:continue
            seen.add(digest)
            target=folder/Path(m.filename).name
            target.write_bytes(data)
            paths.append(target)
            if len(paths)==COUNT:break
    assert len(paths)==COUNT
    print("REAL_DISTINCT_COCO_PHOTOS",len(paths),sum(p.stat().st_size for p in paths),flush=True)
    return paths

def fixtures(folder,photos):
    from PIL import Image
    png=folder/"normalization.png"
    with Image.open(photos[-1]) as image:image.convert("RGB").save(png)
    # MOV forces the actual video preparation path; PNG replaces one JPEG.
    video=folder/"codec-fixture.mov"
    subprocess.run(["ffmpeg","-v","error","-y","-loop","1","-i",str(photos[0]),"-t","2","-vf","scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2","-r","12","-threads","1","-c:v","libx264","-pix_fmt","yuv420p",str(video)],check=True)
    return [*photos[:-1],png,video]


def transfer(s,url,p,*,resume=False):
    data=p.read_bytes()
    if resume:
        split=max(1,len(data)//2)
        assert obj(s,"PATCH",url,data=data[:split],headers={"upload-offset":"0"})["offset"]==split
        # Separate connection/session; server-reported durable offset.
        s=client()
        state=obj(s,"GET",url)
        offset=state.get("offset",state.get("received"))
        assert offset==split
    else:offset=0
    while offset<len(data):
        block=data[offset:offset+CHUNK]
        assert obj(s,"PATCH",url,data=block,headers={"upload-offset":str(offset)})["offset"]==offset+len(block)
        offset+=len(block)
    obj(s,"POST",url+"/finish")

def references(s,photos):
    for region in ("SAM","SZR"):obj(s,"POST","/api/regions",json={"code":region})
    sid=str(uuid.uuid4())
    obj(s,"POST","/api/reference-imports",json={"client_session_id":sid})
    items=[]
    for i,p in enumerate(photos):
        sam=f"{'SAM' if i%2==0 else 'SZR'} {9900+i:04}"
        items.append({"upload_id":str(uuid.uuid4()),"sam":sam,"address":f"CI dataset {i}","relative_path":f"{sam} — CI dataset {i}/{p.name}","filename":p.name,"size":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
    base=f"/api/reference-imports/{sid}"
    obj(s,"PUT",base+"/manifest",json={"files":items})
    for i,(item,p) in enumerate(zip(items,photos)):
        transfer(s,base+"/files/"+item["upload_id"],p,resume=i==0)
    obj(s,"POST",base+"/complete")
    def ready():
        state=obj(s,"GET",base)
        if state["preparation_state"] in ("failed","stopped"):raise RuntimeError(str(state))
        return state["preparation_state"]=="completed"
    wait(ready,timeout=1800,description="reference preparation")
    refs=obj(s,"GET","/api/references/files")["files"]
    assert len(refs)==len(items)
    for i,item in enumerate(refs):
        obj(s,"PATCH","/api/references/"+quote(item["sam"],safe="")+"/sides",json={"photo_ids":[item["id"]],"side":"A1" if i%2==0 else "B2"})
    obj(s,"PATCH","/api/references/constructions/"+quote(refs[0]["sam"],safe="")+"/address",json={"address":"CI renamed construction"})
    return refs

def upload_batch(s,paths,cycle):
    bid=obj(s,"POST","/api/batches",json={"display_name":f"STAGE10_LOAD_{cycle}","report_date_mode":"manual","report_date":"2026-01-02"})["batch_id"]
    items=[{"upload_id":str(uuid.uuid4()),"relative_path":"dataset/"+p.name,"filename":p.name,"size":p.stat().st_size} for p in paths]
    obj(s,"PUT",f"/api/batches/{bid}/upload-manifest",json={"files":items,"image_format":"jpg","video_format":"mp4","auto_process":False})
    local=threading.local()
    def send(pair):
        i,(item,p)=pair
        if not hasattr(local,"session"):local.session=client()
        c=local.session
        obj(c,"POST","/api/uploads",json={"kind":"fo","batch_id":bid,"client_upload_id":item["upload_id"],"filename":p.name,"size":item["size"],"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
        transfer(c,"/api/uploads/"+item["upload_id"],p,resume=i==0)
    start=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(send,enumerate(zip(items,paths))))
    print("UPLOAD_COMPLETE",cycle,len(paths),"seconds",round(time.monotonic()-start,3),flush=True)
    def normalized():
        detail=obj(s,"GET",f"/api/batches/{bid}")
        prep=detail.get("media_preparation")
        if prep and prep["state"] in ("failed","stopped","completed_with_errors"):raise RuntimeError(str(prep))
        return detail if detail["upload_manifest_state"]=="complete" and (not prep or prep["state"]=="completed") else None
    detail=wait(normalized,timeout=1800,description="normalization")
    assert detail["photos"]+detail["videos"]==len(paths),detail
    return bid

def run_sort(s,bid):
    start=time.monotonic()
    rid=obj(s,"POST","/api/runs",json={"batch_id":bid,"grouping_threshold":.99,"regions":["SAM","SZR"]})["id"]
    def terminal():
        info=obj(s,"GET","/api/runs/"+rid)
        if info["status"] in ("failed","stopped","interrupted","completed_with_errors"):raise RuntimeError(str(info)[:1500])
        return info if info["status"]=="completed" else None
    info=wait(terminal,timeout=7200,period=5,description="actual MegaLoc processing")
    print("REAL_SORT_COMPLETE",rid,"seconds",round(time.monotonic()-start,3),json.dumps(info["models"]["megaloc"].get("performance",{})),flush=True)
    return rid,info,time.monotonic()-start

def gallery(s,rid,count):
    cursor=None
    rows=[]
    while True:
        suffix="?limit=60"+("&cursor="+quote(str(cursor),safe="") if cursor else "")
        page=obj(s,"GET",f"/api/results/{rid}/photos"+suffix)
        rows+=page["photos"]
        cursor=page["next_cursor"]
        if cursor is None:break
    assert len(rows)==count,(len(rows),count)
    assert len({r["index"] for r in rows})==count
    return rows

def zip_download(s,path,destination,expected=None,date=False):
    start=time.monotonic()
    with req(s,"GET",path,stream=True,timeout=600) as response,destination.open("wb") as out:
        for chunk in response.iter_content(1024*1024):out.write(chunk)
    with zipfile.ZipFile(destination) as z:
        names=z.namelist()
        assert names and z.testzip() is None
        if expected is not None:assert len(names)==expected,(len(names),expected)
        if date:assert all("/2026-01-02/" in n for n in names)
    response=req(s,"GET",path,headers={"Range":"bytes=0-63"},stream=True)
    try:assert response.status_code==206 and next(response.iter_content(64))==destination.open("rb").read(64)
    finally:response.close()
    size=destination.stat().st_size
    print("ZIP_DOWNLOADED",path,len(names),size,"seconds",round(time.monotonic()-start,3),flush=True)
    destination.unlink()
    return names,size

def settle(s,request=True):
    if request:obj(s,"POST","/api/storage/reconcile")
    started=time.monotonic()
    def ready():
        data=obj(s,"GET","/api/storage/usage")
        reg=data["registry"]
        return data if not reg["partial"] and reg["reconciled_at"] else None
    data=wait(ready,timeout=600,period=2,description="registry reconciliation")
    print("REGISTRY_SETTLED_SECONDS",round(time.monotonic()-started,3),"files",sum(x["files"] for x in data["registry"]["categories"].values()),flush=True)
    return data

def physical():
    # One traversal, GNU du's default hardlink deduplication; registry samples
    # are kept separately. No attribution of external Docker/OS blocks to MAP.
    return int(subprocess.check_output(["du","-s","-B1",str(STORAGE)],text=True).split()[0])

def storage_snapshot(s,label):
    data=settle(s)
    row={"label":label,"at":time.time(),"host_storage_allocated_bytes":physical(),"disk":data["disk"],"registry":data["registry"],"limits":obj(s,"GET","/api/storage/limits")}
    print("STAGE10_STORAGE_SNAPSHOT",json.dumps(row,ensure_ascii=False,separators=(",",":")),flush=True)
    return row

def sampler(stop,samples):
    s=client()
    while not stop.is_set():
        try:
            start=time.monotonic()
            usage=obj(s,"GET","/api/storage/usage")
            latency=time.monotonic()-start
            start=time.monotonic()
            obj(s,"GET","/api/batches?limit=20")
            batch_latency=time.monotonic()-start
            ids=output("ps","-q").splitlines()
            stats=subprocess.check_output(["docker","stats","--no-stream","--format","{{json .}}",*ids],text=True)
            samples.append({"at":time.time(),"storage_api_seconds":latency,"batches_api_seconds":batch_latency,"disk":usage["disk"],"temporary":usage["registry"].get("temporary"),"temporary_peak_bytes":usage["registry"].get("temporary_peak_bytes"),"pending_changes":usage["registry"].get("pending_changes"),"stats":[json.loads(line) for line in stats.splitlines()]})
        except Exception as exc:
            samples.append({"at":time.time(),"error":str(exc)[:250]})
        stop.wait(10)

def browser_probe(stop,samples):
    # Real Chromium, real backend, not mocked Playwright routes.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
        context=browser.new_context(ignore_https_errors=True)
        page=context.new_page()
        page.goto(BASE+"/admin",wait_until="domcontentloaded")
        page.get_by_label("Электронная почта или логин").fill("admin")
        page.get_by_label("Пароль",exact=True).fill(PASSWORD)
        page.get_by_role("button",name="Продолжить").click()
        page.get_by_role("region",name="Хранилище").wait_for(timeout=60000)
        while not stop.is_set():
            try:
                start=time.monotonic()
                page.goto(BASE+"/admin",wait_until="domcontentloaded",timeout=60000)
                page.get_by_role("heading",name="Объём хранилища").wait_for(timeout=60000)
                samples.append({"at":time.time(),"browser_storage_seconds":time.monotonic()-start})
            except Exception as exc:samples.append({"at":time.time(),"browser_error":str(exc)[:250]})
            stop.wait(30)
        browser.close()

def expire(s):
    # Keep the production 3600-second policy intact. Only age disposable
    # cache files so the real cleanup worker observes the final 60 seconds.
    ttl=int(app_python("from server.services.archive_cache import TTL_SECONDS;print(TTL_SECONDS)"))
    assert ttl==3600,ttl
    archives=STORAGE/"app/temporary/archives"
    paths=list(archives.rglob("*.zip"))
    assert paths
    start=time.monotonic()
    stamp=time.time()-(ttl-ZIP_TEST_REMAINING_SECONDS)
    for path in paths:
        os.utime(path,(stamp,stamp))
    time.sleep(10)
    assert all(path.is_file() for path in paths),"ZIP expired before its deadline"
    wait(lambda:not list(archives.rglob("*.zip")),timeout=150,period=2,description="automatic ZIP expiration")
    elapsed=time.monotonic()-start
    assert elapsed>=ZIP_TEST_REMAINING_SECONDS-1,elapsed
    result={"elapsed_seconds":round(elapsed,3),"production_ttl_seconds":ttl,"remaining_seconds":ZIP_TEST_REMAINING_SECONDS,"files":len(paths)}
    print("ZIP_AUTO_EXPIRY",result,flush=True)
    return result

def assert_batch_hardlinks(bid,rid,count):
    batches=list((STORAGE/"app/users").glob(f"*/batches/{bid}"))
    assert len(batches)==1,batches
    batch=batches[0]
    def inode(path):
        stat=path.stat()
        return (stat.st_dev,stat.st_ino)
    source={inode(p) for folder in ("originals","normalized") for p in (batch/folder).rglob("*") if p.is_file()}
    media=[p for p in (batch/"results"/rid/"media").rglob("*") if p.is_file()]
    assert len(media)==count,(len(media),count)
    assert all(inode(p) in source for p in media),"same-filesystem result was not hardlinked"
    return len(media)

def assert_released_media(snapshot,baseline):
    # Persistent model, PostgreSQL and log bytes may legitimately grow.
    # Batch-owned file categories and temporary payloads must not.
    current=snapshot["registry"]["categories"]
    previous=baseline["registry"]["categories"]
    for category in ("fo_original","fo_normalized","result_media","result_metadata","fo_thumbnail","fo_upload_part","transcode_temp","video_frames","processing_staging","fo_embedding_temp"):
        actual=current.get(category,{}).get("files",0)
        expected=previous.get(category,{}).get("files",0)
        assert actual==expected,(category,actual,expected)

def delete_batch(s,bid):
    obj(s,"DELETE",f"/api/batches/{bid}")
    wait(lambda:obj(s,"GET",f"/api/batches/{bid}/deletion").get("delete_state")=="deleted",timeout=600,description="batch deletion")
    # The expected thumbnail grace is tested by the real collector on aged
    # fixtures after dependency disappearance, not a new production policy.
    print("BATCH_DELETED",bid,flush=True)

def quota_probe(s,photo):
    account=next(x for x in obj(s,"GET","/api/storage/accounts")["rows"] if x["access_role"]=="owner")
    owner=account["id"]
    bid=obj(s,"POST","/api/batches",json={"display_name":"CI quota probe"})["batch_id"]
    file_id=str(uuid.uuid4())
    entry={"upload_id":file_id,"relative_path":"quota/"+photo.name,"filename":photo.name,"size":photo.stat().st_size}
    obj(s,"PUT",f"/api/batches/{bid}/upload-manifest",json={"files":[entry],"image_format":"jpg","video_format":"mp4","auto_process":False})
    payload={"kind":"fo","batch_id":bid,"client_upload_id":file_id,"filename":photo.name,"size":entry["size"]}
    settle(s)
    obj(s,"PATCH",f"/api/storage/accounts/{owner}/limit",json={"limit_bytes":0})
    obj(s,"PATCH","/api/storage/limits",json={"personal_enabled":True})
    try:
        response=s.post(BASE+"/api/uploads",json=payload,timeout=30)
        assert response.status_code==507,response.text
        obj(s,"PATCH","/api/storage/limits",json={"personal_enabled":False,"temporary_limit_bytes":0})
        response=s.post(BASE+"/api/uploads",json=payload,timeout=30)
        assert response.status_code==507,response.text
    finally:
        obj(s,"PATCH","/api/storage/limits",json={"personal_enabled":False})
        obj(s,"PATCH",f"/api/storage/accounts/{owner}/limit",json={"limit_bytes":None})
    delete_batch(s,bid)
    print("STAGE10_HTTP_QUOTA_REJECTION_OK",flush=True)

def main():
    if os.geteuid()!=0 or os.environ.get("CI")!="true" or os.environ.get("GITHUB_ACTIONS")!="true" or STORAGE.exists() or (ROOT/".env").exists():
        raise RuntimeError("Requires a fresh disposable GitHub Actions checkout, root")
    folder=Path(sys.argv[1]).resolve()
    archive=Path(sys.argv[2]).resolve()
    report=Path(sys.argv[3]).resolve()
    photos=dataset(archive,folder)
    paths=fixtures(folder,photos)
    assert len(paths)==COUNT+VIDEO_COUNT
    env=dict(os.environ,GIT_CONFIG_COUNT="1",GIT_CONFIG_KEY_0="safe.directory",GIT_CONFIG_VALUE_0=str(ROOT))
    # Fixture runner is disposable, configure the same installer as a real VPS.
    subprocess.run(["bash","install.sh","--configure"],cwd=ROOT,input=f"localhost\n{PASSWORD}\n",text=True,env=env,check=True)
    wait(lambda:requests.get(BASE+"/api/health",verify=False,timeout=10).ok,timeout=180)
    s=client()
    obj(s,"POST","/api/models/megaloc/download")
    wait(lambda:obj(s,"GET","/api/models")["models"][0]["available"],timeout=1800,description="official MegaLoc download")
    refs=references(s,photos[:8])
    initial=storage_snapshot(s,"baseline_after_reference_preparation")
    assert not initial["limits"]["policy"]["personal_enabled"] and initial["limits"]["policy"]["temporary_limit_bytes"] is None
    quota_probe(s,photos[0])
    stamps=app_python("from pathlib import Path;from app import config;import json;print(json.dumps({str(p):(p.stat().st_ino,p.stat().st_mtime_ns) for p in (config.APP_STORAGE_ROOT/'shared/references/embeddings').rglob('*.npy')},sort_keys=True))")
    assert len(json.loads(stamps))==8
    samples=[];browser_samples=[];cycles=[];final=None;stop=threading.Event()
    thread=threading.Thread(target=sampler,args=(stop,samples),daemon=True)
    browser_thread=threading.Thread(target=browser_probe,args=(stop,browser_samples),daemon=True)
    thread.start();browser_thread.start()
    try:
        for cycle in range(1,4):
            bid=upload_batch(s,paths,cycle)
            uploaded=storage_snapshot(s,f"cycle_{cycle}_uploaded")
            rid,info,seconds=run_sort(s,bid)
            rows=gallery(s,rid,len(paths))
            assert len([r for r in rows if r.get("media_kind")=="video"])==VIDEO_COUNT
            hardlinks=assert_batch_hardlinks(bid,rid,len(paths))
            if cycle==1:
                assert any(r.get("side") in ("A1","B2") for r in rows)
                # Reprocessing does not replace the previous run or recompute refs.
                # Repeat on a later small cycle to keep full real load bounded.
                viewer=obj(s,"POST","/api/admin/users",json={"email":"ci-viewer@example.test","password":PASSWORD,"confirmation":PASSWORD,"run_ids":[rid]})
                v=client("ci-viewer@example.test",PASSWORD)
                assert obj(v,"GET","/api/results/"+rid)["id"]==rid
                assert v.get(BASE+"/api/storage/limits",timeout=20).status_code==403
                assert v.get(BASE+"/api/batches",timeout=20).status_code==403
                assert v.patch(BASE+"/api/storage/limits",json={"personal_enabled":True},timeout=20).status_code==403
            if cycle==2:
                second,_,_=run_sort(s,bid)
                assert second!=rid
                gallery(s,second,len(paths))
                assert_batch_hardlinks(bid,second,len(paths))
                rid=second
            assert app_python("from pathlib import Path;from app import config;import json;print(json.dumps({str(p):(p.stat().st_ino,p.stat().st_mtime_ns) for p in (config.APP_STORAGE_ROOT/'shared/references/embeddings').rglob('*.npy')},sort_keys=True))")==stamps
            sorted_state=storage_snapshot(s,f"cycle_{cycle}_sorted")
            if cycle==1:
                # All three ZIP paths are real HTTP downloads with CRC and Range.
                names,size=zip_download(s,"/api/download/"+rid,folder/"download.zip",len(paths),True)
                sam=next(r["assigned_sam"] for r in rows if r["assigned_sam"] and not r["assigned_sam"].startswith("_"))
                zip_download(s,"/api/download/"+rid+"?sam="+quote(sam,safe=""),folder/"construction.zip",sum(r["assigned_sam"]==sam for r in rows),True)
                zip_download(s,"/api/references/export",folder/"references.zip",len(refs))
            else:names,size=zip_download(s,"/api/download/"+rid,folder/"download.zip",len(paths),True)
            zipped=storage_snapshot(s,f"cycle_{cycle}_zipped")
            expiry=expire(s)
            expired=storage_snapshot(s,f"cycle_{cycle}_expired")
            delete_batch(s,bid)
            # Accelerate only the existing thumbnail grace, on disposable data.
            app_python("from server.services.thumbnails import gc_unowned;print(gc_unowned(limit=2000,grace_seconds=0))")
            deleted=storage_snapshot(s,f"cycle_{cycle}_deleted")
            assert not any(p.is_file() for batch in (STORAGE/"app/users").glob(f"*/batches/{bid}") for p in batch.rglob("*"))
            assert_released_media(deleted,initial)
            assert deleted["limits"]["disk"]["reserved_bytes"]==0,deleted["limits"]
            cycles.append({"cycle":cycle,"files":len(paths),"photos":COUNT,"videos":VIDEO_COUNT,"hardlinks":hardlinks,"zip_expiry":expiry,"sort_seconds":seconds,"zip_bytes":size,"uploaded":uploaded,"sorted":sorted_state,"zipped":zipped,"expired":expired,"deleted":deleted})
        # Active grants do not own media; deleted FO releases run pins.
        for ref in refs:obj(s,"DELETE","/api/references/files/"+ref["id"])
        # Explicitly test dependency/grace policy using existing collector;
        # no artificial age change in production and no forced protected purge.
        app_python("from server.services.reference_gc import collect;print(collect(limit=100,history_grace=0,grace_seconds=0))")
        app_python("from server.services.reference_gc import collect;print(collect(limit=100,history_grace=0,grace_seconds=0))")
        final=storage_snapshot(s,"final_after_reference_cleanup")
        assert sql("SELECT count(*) FROM reference_cache")=="0"
        assert sql("SELECT count(*) FROM reference_physical_objects")=="0"
        assert final["limits"]["disk"]["reserved_bytes"]==0
        assert obj(s,"GET","/api/storage/accounts")["total"]>=2
        for path in ("/api/storage/operations","/api/storage/accounting/issues","/api/storage/maintenance","/api/storage/breakdown"):
            obj(s,"GET",path)
        assert not (ROOT/"PhotoSorter/data").exists() and not (ROOT/"Models").exists()
        assert samples and any("stats" in x for x in samples)
        assert any("browser_storage_seconds" in x for x in browser_samples),browser_samples
        print("STAGE10_REAL_LOAD_COMPLETE",flush=True)
    finally:
        stop.set();thread.join(timeout=150);browser_thread.join(timeout=150)
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps({"source":"COCO val2017 distinct photos; generated codec videos; not outdoor quality ground truth","count":COUNT,"videos":VIDEO_COUNT,"baseline":initial,"final":final,"cycles":cycles,"samples":samples,"browser_samples":browser_samples,"host":{"cpu_count":os.cpu_count(),"meminfo":Path("/proc/meminfo").read_text().splitlines()[:3]}},ensure_ascii=False,indent=2))
        for key in ("storage_api_seconds","batches_api_seconds","browser_storage_seconds"):
            vals=[x[key] for x in samples+browser_samples if key in x]
            if vals:print("MEASURED_LATENCY",key,"count",len(vals),"median",statistics.median(vals),"max",max(vals),flush=True)

if __name__=="__main__":main()
