"""Account acceptance: real API sessions, PostgreSQL, files, registry and recovery.

Runs in the existing backend CI, using the disposable schema and temporary
storage fixture. No model inference, Docker or VM required.
"""
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from app import config
from app.results.exporter import MANIFEST_NAME
from app.results.repository import load_model
from server import auth, database
from server.db import migration_runner
from server.security.login_throttle import LoginThrottle
from server.services import account_lifecycle, cleanup, reference_publication
from server.storage import admission, registry, thumbnail_cache
from server.storage.paths import original_path, result_media_dir, result_metadata_dir, batch_root
from .accounting_checks import settle, exact
from .test_unified_queue_stage3 import system
from .test_access_requests import client, login, OWNER, PASSWORD
from .test_stage2_platform import _jpg

def clients(monkeypatch):
    monkeypatch.setenv('DOMAIN','sorter.example.test')
    monkeypatch.setenv('ADMIN_PASSWORD',OWNER)
    monkeypatch.setattr(auth,'limiter',LoginThrottle())
    auth.bootstrap_admin()
    admin=client()
    assert login(admin,'admin',OWNER).status_code==200
    return admin

def create_user(admin,name,role='employee',overrides=None):
    res=admin.post('/api/admin/users',json={'email':name,'password':PASSWORD,
        'confirmation':PASSWORD,'role_id':role,'overrides':overrides or {},'run_ids':[]})
    assert res.status_code==201,res.text
    browser=client()
    assert login(browser,name,PASSWORD).status_code==200
    return res.json()['id'],browser

def create_batch(browser,name):
    res=browser.post('/api/batches',json={'display_name':name})
    assert res.status_code==200,res.text
    return uuid.UUID(res.json()['batch_id'])

def seed_photo(batch,owner):
    uid=uuid.uuid4();raw=_jpg()
    path=original_path(batch,uid,'jpg',owner)
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    checksum=hashlib.sha256(raw).hexdigest()
    with database.connect() as db:
        db.execute("""INSERT INTO uploads(id,kind,batch_id,filename,declared_size,
            received,checksum,finalized,target_path) VALUES(%s,'fo',%s,'photo.jpg',%s,%s,%s,true,%s)""",
            (uid,batch,len(raw),len(raw),checksum,str(path)))
    return uid,path,checksum

def seed_result(batch,owner,path):
    run='20261126T180000-'+uuid.uuid4().hex[:12]
    with database.connect() as db:
        db.execute("INSERT INTO jobs(id,batch_id,status,snapshot) VALUES(%s,%s,'completed',%s)",
          (run,batch,Jsonb({'id':run,'batch_id':str(batch),'status':'completed','new_photos':str(path.parent),
                           'models':{'megaloc':{'status':'completed','processed':1}}})))
    media=result_media_dir(run);media.mkdir(parents=True)
    copied=media/'photo.jpg';os.link(path,copied)
    metadata=result_metadata_dir(run);metadata.mkdir(parents=True)
    (metadata/MANIFEST_NAME).write_text(json.dumps({'index':0,'query':path.relative_to(batch_root(batch,owner)).as_posix(),
        'copy':'photo.jpg','assigned_sam':'SAM 0001','group_id':'G0001'})+'\n',encoding='utf-8')
    return run,copied

def test_scoped_api_and_live_overrides(system,monkeypatch):
    admin=clients(monkeypatch)
    alice,a=create_user(admin,'alice@example.test')
    bob,b=create_user(admin,'bob@example.test')
    first=create_batch(a,'Alice report');second=create_batch(b,'Bob report')
    ap,_,_=seed_photo(first,alice);bp,_,_=seed_photo(second,bob)
    own=f'/api/batches/{first}';foreign=f'/api/batches/{second}'
    assert {v['batch_id'] for v in a.get('/api/batches').json()['batches']}=={str(first)}
    assert a.get(own).status_code==200
    assert a.get(f'/api/photos/{ap}/original').status_code==200
    for url in (foreign,foreign+'/gallery',f'/api/photos/{bp}/original',f'/api/thumbnails/{bp}'):
        assert a.get(url).status_code==404,url
    assert a.patch(foreign,json={'display_name':'forbidden'}).status_code==404
    assert a.delete(foreign).status_code==404
    assert a.post('/api/uploads',json={'kind':'fo','filename':'x.jpg','size':100,'batch_id':str(second)}).status_code==404
    assert a.post('/api/runs',json={'batch_id':str(second)}).status_code==404
    assert a.get('/api/admin/accounts').status_code==403
    edit=f'/api/admin/accounts/{alice}'
    payload={'display_name':'Alice','role_id':'employee','overrides':{'photos.view':'all'}}
    assert admin.put(edit,json=payload).status_code==200
    assert a.get(foreign).status_code==200
    assert a.get(foreign+'/gallery').status_code==404
    assert a.delete(foreign).status_code==404
    assert a.patch(own,json={'display_name':'Renamed own report'}).status_code==200
    payload['overrides']['photos.view']='none'
    assert admin.put(edit,json=payload).status_code==200
    assert a.get(own).status_code==403
    assert a.get(f'/api/photos/{ap}/original').status_code==403
    assert admin.post(edit+'/security',json={'action':'block','confirmed':True}).status_code==200
    assert a.get('/api/auth/me').status_code==401
    assert login(a,'alice@example.test',PASSWORD).status_code==401
    assert admin.post(edit+'/security',json={'action':'unblock','confirmed':True}).status_code==200
    assert login(a,'alice@example.test',PASSWORD).status_code==200

def test_delegation_cannot_escalate_or_take_over_owner(system,monkeypatch):
    admin=clients(monkeypatch)
    delegate,d=create_user(admin,'delegate@example.test','administrator',
        {'accounts.role_edit':'all','accounts.role_delete':'all'})
    staff,s=create_user(admin,'staff@example.test')
    with database.connect() as db:owner=db.execute("SELECT id FROM users WHERE username='admin'").fetchone()['id']
    endpoint='/api/admin/accounts/'
    assert d.get('/api/admin/accounts').status_code==200
    assert d.put(endpoint+str(staff),json={'display_name':'Managed','role_id':'employee','overrides':{}}).status_code==200
    assert d.put(endpoint+str(delegate),json={'display_name':'Self','role_id':'employee','overrides':{}}).status_code==403
    assert d.put(endpoint+str(staff),json={'display_name':'Escalation','role_id':'administrator','overrides':{}}).status_code==403
    assert d.put(endpoint+str(staff),json={'display_name':'Escalation','role_id':'employee','overrides':{'system.update':'all'}}).status_code==403
    assert d.post(endpoint+str(owner)+'/security',json={'action':'reset_password','password':PASSWORD,'confirmed':True}).status_code==403
    assert d.post(endpoint+str(owner)+'/security',json={'action':'block','confirmed':True}).status_code==403
    assert d.post(endpoint+str(owner)+'/lifecycle',json={'operation':'delete','confirmation':'admin'}).status_code==403
    assert d.post(endpoint+'roles',json={'name':'Escalation','permissions':{'accounts.assign':'all'}}).status_code==403
    assert d.put(endpoint+'roles/administrator',json={'name':'Hijack','permissions':{'photos.view':'all'}}).status_code==403
    role=d.post(endpoint+'roles',json={'name':'Read own','permissions':{'photos.view':'own'}})
    assert role.status_code==201,role.text
    assert d.put(endpoint+str(staff),json={'display_name':'Managed','role_id':role.json()['id'],'overrides':{}}).status_code==200
    assert s.get('/api/batches').status_code==200
    assert s.post('/api/batches',json={'display_name':'Denied'}).status_code==403
    assert d.put(endpoint+'roles/'+role.json()['id'],json={'name':'Read own','permissions':{'photos.view':'none'}}).status_code==200
    assert s.get('/api/batches').status_code==403
    with database.connect() as db:
        assert db.execute("SELECT blocked,role_id FROM users WHERE id=%s",(owner,)).fetchone()=={'blocked':False,'role_id':'owner'}

@pytest.mark.parametrize('operation,interrupt',[('transfer',False),('transfer_delete',True)])
def test_transfer_quota_and_recovery_then_delete(system,monkeypatch,operation,interrupt):
    admin=clients(monkeypatch)
    source,a=create_user(admin,'source@example.test')
    target,b=create_user(admin,'target@example.test')
    batch=create_batch(a,'Transfer me')
    upload,original,digest=seed_photo(batch,source)
    run,copy=seed_result(batch,source,original)
    thumb=thumbnail_cache.location(digest,owner_id=source)
    thumb.parent.mkdir(parents=True,exist_ok=True);thumb.write_bytes(b'derived preview')
    # Shared data must never be deleted with an account.
    from app.storage.categories import Category
    from app.storage.paths import managed_path
    shared=managed_path(Category.REFERENCE_THUMBNAIL,version=1,prefix=digest[:2],hash=digest)
    shared.parent.mkdir(parents=True,exist_ok=True);shared.write_bytes(b'shared preview')
    inode=original.stat().st_ino
    settle()
    def budget(owner):
        with database.connect() as db:return admission.account_budget(db,owner)
    charged=budget(source)['used_bytes']
    assert charged>0 and exact(original)['owner_id']==source
    admission.configure({'personal_enabled':True,'temporary_limit_bytes':None,'disk_reserve_bytes':None})
    admission.set_account(target,charged-1)
    endpoint=f'/api/admin/accounts/{source}/lifecycle'
    body={'operation':operation,'recipient_id':target,'confirmation':'source@example.test'}
    assert admin.post(endpoint,json=body).status_code==409
    assert original.is_file() and a.get('/api/auth/me').status_code==200
    admission.set_account(target,charged)
    assert admin.post(endpoint,json={**body,'confirmation':'wrong'}).status_code==422
    assert admin.post(endpoint,json=body).status_code==202
    assert a.get('/api/auth/me').status_code==401
    assert admin.post(endpoint,json=body).status_code==409
    from server.services.account_activity import lease
    # A real queued transfer cannot start while an API reader is active.
    with lease() as allowed:
        assert allowed
        account_lifecycle.run_pending()
        assert original.is_file()
        with database.connect() as db:
            assert db.execute("SELECT plan FROM account_lifecycle WHERE source_id=%s",(source,)).fetchone()['plan'] is None
    if interrupt:
        real_move=account_lifecycle._move
        def fail_after_move(root,entry):
            real_move(root,entry)
            if entry['kind']=='file':raise RuntimeError('simulated termination after rename')
        monkeypatch.setattr(account_lifecycle,'_move',fail_after_move)
        account_lifecycle.run_pending()
        with database.connect() as db:
            state=db.execute("SELECT state,plan FROM account_lifecycle WHERE source_id=%s",(source,)).fetchone()
            assert state['state']=='retry' and state['plan']['files']
            assert db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch,)).fetchone()['owner_id']==source
        assert not original.exists()
        # Accounting is allowed to see the moved files between attempts.
        settle()
        monkeypatch.setattr(account_lifecycle,'_move',real_move)
        with database.connect() as db:db.execute("UPDATE account_lifecycle SET next_attempt=now() WHERE source_id=%s",(source,))
    # Check the actual API during the physical rename and after publication.
    real_move=account_lifecycle._move
    checked=[]
    def guarded_move(root,entry):
        assert admin.get('/api/models').status_code==503
        checked.append(entry)
        real_move(root,entry)
    monkeypatch.setattr(account_lifecycle,'_move',guarded_move)
    account_lifecycle.run_pending()
    assert checked and admin.get('/api/models').status_code==200
    monkeypatch.setattr(account_lifecycle,'_move',real_move)
    moved=original_path(batch,upload,'jpg',target)
    assert moved.is_file() and moved.stat().st_ino==inode and not original.exists()
    assert (result_media_dir(run)/copy.name).stat().st_ino==inode
    assert load_model(run,'megaloc')[0]['query']==str(moved)
    assert thumbnail_cache.location(digest,owner_id=target).read_bytes()==b'derived preview'
    assert exact(moved)['owner_id']==target
    assert budget(source)['used_bytes']==0 and budget(target)['used_bytes']==charged
    assert b.get(f'/api/photos/{upload}/original').status_code==200
    assert b.get('/api/results/'+run).status_code==200
    if operation=='transfer':
        assert login(a,'source@example.test',PASSWORD).status_code==200
        assert a.get(f'/api/photos/{upload}/original').status_code==404
        assert a.get('/api/results/'+run).status_code==404
    else:
        with database.connect() as db:db.execute("UPDATE account_lifecycle SET next_attempt=now() WHERE source_id=%s",(source,))
        account_lifecycle.run_pending()
        assert admin.get(endpoint).status_code==404
    # Now delete the recipient using the ordinary durable batch cleanup.
    delete=f'/api/admin/accounts/{target}/lifecycle'
    assert admin.post(delete,json={'operation':'delete','confirmation':'target@example.test'}).status_code==202
    account_lifecycle.run_pending()
    assert cleanup.cleanup_one(batch)=='completed'
    settle()
    with database.connect() as db:db.execute("UPDATE account_lifecycle SET next_attempt=now() WHERE source_id=%s",(target,))
    account_lifecycle.run_pending()
    assert admin.get(delete).status_code==404
    assert b.get('/api/auth/me').status_code==401
    assert not moved.exists() and shared.read_bytes()==b'shared preview'
    with database.connect() as db:
        assert not db.execute("SELECT 1 FROM storage_files WHERE owner_id=%s",(target,)).fetchone()
        assert not db.execute("SELECT 1 FROM batches WHERE owner_id=%s",(target,)).fetchone()
        assert not db.execute("SELECT 1 FROM sessions WHERE user_id=%s",(target,)).fetchone()

def test_legacy_migration_preserves_user_grant_session_quota(tmp_path,monkeypatch):
    if not database.DB_URL:pytest.skip('Requires disposable PostgreSQL')
    url=database.DB_URL;schema='accounts_'+uuid.uuid4().hex
    with psycopg.connect(url,autocommit=True) as root:
        root.execute('CREATE SCHEMA '+schema)
        try:
            monkeypatch.setattr(database,'DB_URL',make_conninfo(url,options='-c search_path='+schema))
            monkeypatch.setattr(config,'APP_STORAGE_ROOT',tmp_path/'app');config.APP_STORAGE_ROOT.mkdir()
            monkeypatch.setattr(reference_publication,'signature',lambda:'a'*64)
            monkeypatch.setenv('DOMAIN','sorter.example.test')
            monkeypatch.setenv('ADMIN_PASSWORD',OWNER)
            monkeypatch.setattr(auth,'limiter',LoginThrottle())
            migrations=migration_runner.MIGRATIONS;old=tmp_path/'migrations';old.mkdir()
            for p in migrations.glob('*.sql'):
                if p.name[:4]<'0049':shutil.copy2(p,old/p.name)
            monkeypatch.setattr(migration_runner,'MIGRATIONS',old)
            database.initialize()
            salt=b'0123456789abcdef';verifier=auth.hash_password(PASSWORD,salt)
            token='legacy_session_token'
            run='20261126T170000-0123456789ab';batch=uuid.uuid4()
            with database.connect() as db:
                owner=db.execute("INSERT INTO users(username,access_role) VALUES('admin','owner') RETURNING id").fetchone()['id']
                viewer=db.execute("""INSERT INTO users(username,access_role,password_salt,password_hash,storage_limit_bytes)
                    VALUES('legacy@example.test','viewer',%s,%s,123456) RETURNING id""",(salt.hex(),verifier)).fetchone()['id']
                db.execute("INSERT INTO batches(id,display_name,owner_id) VALUES(%s,'Legacy report',%s)",(batch,owner))
                db.execute("INSERT INTO jobs(id,batch_id,status,snapshot) VALUES(%s,%s,'completed',%s)",(run,batch,Jsonb({'id':run})))
                db.execute("INSERT INTO result_access_grants(user_id,run_id) VALUES(%s,%s)",(viewer,run))
                db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(%s,%s,%s)",(hashlib.sha256(token.encode()).hexdigest(),viewer,datetime.now(timezone.utc)+timedelta(days=1)))
            shutil.copy2(migrations/'0049_account_roles.sql',old/'0049_account_roles.sql')
            database.initialize()
            with database.connect() as db:
                assigned=db.execute("INSERT INTO users(username,access_role,role_id) VALUES('assigned@example.test','viewer','employee') RETURNING id").fetchone()['id']
                before=db.execute("SELECT permissions FROM account_roles WHERE id='employee'").fetchone()
            monkeypatch.setattr(migration_runner,'MIGRATIONS',migrations)
            database.initialize();database.initialize()
            auth.bootstrap_admin()
            with database.connect() as db:
                preserved=db.execute("SELECT id,password_salt,password_hash,storage_limit_bytes,role_id FROM users WHERE id=%s",(viewer,)).fetchone()
                assert preserved=={'id':viewer,'password_salt':salt.hex(),'password_hash':verifier,'storage_limit_bytes':123456,'role_id':'observer'}
                assert db.execute("SELECT owner_id FROM batches WHERE id=%s",(batch,)).fetchone()['owner_id']==owner
                assert db.execute("SELECT permissions FROM account_roles WHERE id='employee'").fetchone()==before
                assert db.execute("SELECT role_id FROM users WHERE id=%s",(assigned,)).fetchone()['role_id']=='employee'
            legacy=client();legacy.cookies.set(auth.COOKIE_NAME,token)
            assert legacy.get('/api/auth/me').json()=={'username':'legacy@example.test'}
            assert [x['id'] for x in legacy.get('/api/results/catalog').json()['items']]==[run]
            assert legacy.get('/api/batches').status_code==403
            assert login(legacy,'legacy@example.test',PASSWORD).status_code==200
            assert login(client(),'admin',OWNER).status_code==200
        finally:root.execute('DROP SCHEMA '+schema+' CASCADE')


def test_idle_lifecycle_and_model_space_keep_real_api_available(system,monkeypatch):
    from server.services import archive_cache
    admin=clients(monkeypatch)
    with database.connect() as db:
        assert db.execute("SELECT count(*) AS n FROM account_lifecycle").fetchone()['n']==0
    # The idle cleanup poll must not even acquire the exclusive account lease.
    def forbidden(*args,**kwargs):
        pytest.fail('idle lifecycle tried to lock API')
    monkeypatch.setattr(account_lifecycle,'lease',forbidden)
    account_lifecycle.run_pending()
    with archive_cache.build_space(config.APP_STORAGE_ROOT,4096,kind='model_download'):
        assert admin.get('/api/models').status_code==200
        account_lifecycle.run_pending()
        assert admin.get('/api/models').status_code==200


def test_personal_favicon_status_never_exposes_other_owners(system,monkeypatch):
    admin=clients(monkeypatch)
    alice,a=create_user(admin,'favicon-alice@example.test',overrides={'queue.view':'all'})
    bob,b=create_user(admin,'favicon-bob@example.test')
    own=create_batch(a,'Alice favicon')
    foreign=create_batch(b,'Bob favicon')
    with database.connect() as db:
        for batch,state,pct in ((own,'running',55),(foreign,'queued',0)):
            run='20261126T180000-'+uuid.uuid4().hex[:12]
            db.execute("INSERT INTO jobs(id,batch_id,status,snapshot) VALUES(%s,%s,%s,%s)",
                       (run,batch,state,Jsonb({'progress':{'overall_percent':pct}})))
            db.execute("INSERT INTO work_queue(kind,fo_run_id,state) VALUES('fo_processing',%s,%s)",(run,state))
    endpoint='/api/work-queue/own-status'
    for browser,account,expected in ((a,alice,'running'),(b,bob,'queued')):
        reply=browser.get(endpoint)
        assert reply.status_code==200,reply.text
        data=reply.json()
        assert data['account_id']==str(account)
        assert len(data['tasks'])==1 and data['tasks'][0]['state']==expected
    assert admin.get(endpoint).json()['tasks']==[]
    assert a.get(endpoint).json()['tasks'][0]['progress']==55
    assert admin.put(f'/api/admin/accounts/{alice}',json={'display_name':'Alice','role_id':'employee','overrides':{'queue.view':'none'}}).status_code==200
    assert a.get(endpoint).status_code==403


def test_extended_personal_activity_is_actor_scoped(system,monkeypatch):
    from server.services.archive_activity import track
    admin=clients(monkeypatch)
    alice,a=create_user(admin,'activity-alice@example.test',overrides={'references.import':'all'})
    bob,b=create_user(admin,'activity-bob@example.test')
    batch=create_batch(a,'Media and cleanup')
    with database.connect() as db:
        sid,pid=uuid.uuid4(),uuid.uuid4()
        db.execute("INSERT INTO reference_import_sessions(id,requested_by) VALUES(%s,%s)",(sid,alice))
        db.execute("INSERT INTO reference_preparation_jobs(id,session_id,total_count,completed_count) VALUES(%s,%s,10,3)",(pid,sid))
        db.execute("INSERT INTO work_queue(kind,reference_job_id,state) VALUES('reference_preparation',%s,'queued')",(pid,))
        db.execute("INSERT INTO work_queue(kind,media_batch_id,media_total_count,media_progress_percent,state) VALUES('media_preparation',%s,10,40,'running')",(batch,))
        db.execute("INSERT INTO cleanup_tasks(batch_id,state) VALUES(%s,'pending')",(batch,))
    endpoint='/api/activity/own'
    assert client().get(endpoint).status_code==401
    with track({'id':alice},'results'):
        response=a.get(endpoint)
        assert response.status_code==200,response.text
        own=response.json()
        assert own['username']=='activity-alice@example.test'
        assert own['account_id']==str(alice)
        assert {x['kind'] for x in own['tasks']}=={'reference','media','cleanup','zip'}
        assert next(x for x in own['tasks'] if x['kind']=='zip')['state']=='running'
        assert b.get(endpoint).json()['tasks']==[]
        assert admin.get(endpoint).json()['tasks']==[]
    assert next(x for x in a.get(endpoint).json()['tasks'] if x['kind']=='zip')['state']=='completed'
    with pytest.raises(RuntimeError):
        with track({'id':alice},'results'):
            raise RuntimeError('test failure')
    assert any(x['kind']=='zip' and x['state']=='failed' for x in a.get(endpoint).json()['tasks'])


def test_global_queue_positions_survive_scoping_and_pagination(system,monkeypatch):
    from server.db.repositories import work_queue
    admin=clients(monkeypatch)
    alice,a=create_user(admin,'queue-alice@example.test')
    bob,b=create_user(admin,'queue-bob@example.test')
    batches=[create_batch(admin,'Private admin'),create_batch(b,'Private Bob'),
             create_batch(a,'Alice first'),create_batch(a,'Alice second')]
    runs=['20261126T180000-'+uuid.uuid4().hex[:12] for _ in batches]
    with database.connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(%s)",(work_queue.LOCK,))
        for batch,run in zip(batches,runs):
            db.execute("INSERT INTO jobs(id,batch_id,status,snapshot) VALUES(%s,%s,'queued',%s)",
                       (run,batch,Jsonb({'id':run,'status':'queued'})))
            work_queue.insert_fo(db,run)
        db.execute("UPDATE jobs SET status='running',started_at=now() WHERE id=%s",(runs[0],))
        db.execute("UPDATE work_queue SET state='running',started_at=now() WHERE fo_run_id=%s",(runs[0],))
    response=a.get('/api/work-queue')
    assert response.status_code==200,response.text
    assert [item['fo_run_id'] for item in response.json()['tasks']]==runs[2:]
    assert [item['queue_position'] for item in response.json()['tasks']]==[3,4]
    assert runs[0] not in response.text and runs[1] not in response.text
    assert 'Private admin' not in response.text and 'Private Bob' not in response.text
    assert a.get('/api/work-queue?limit=1&offset=1').json()['tasks'][0]['queue_position']==4
    assert b.get('/api/work-queue').json()['tasks'][0]['queue_position']==2
    assert [item['queue_position'] for item in admin.get('/api/work-queue').json()['tasks']]==[1,2,3,4]
    assert a.post('/api/runs/'+runs[1]+'/stop').status_code==404
    with database.connect() as db:
        db.execute("UPDATE jobs SET status='completed',finished_at=now() WHERE id=%s",(runs[0],))
        db.execute("UPDATE work_queue SET state='completed',finished_at=now() WHERE fo_run_id=%s",(runs[0],))
    assert [item['queue_position'] for item in a.get('/api/work-queue').json()['tasks']]==[2,3]
    assert b.post('/api/runs/'+runs[1]+'/stop').status_code==200
    assert [item['queue_position'] for item in a.get('/api/work-queue').json()['tasks']]==[1,2]


def test_result_catalog_metadata_scoped_to_result_permissions(system,monkeypatch):
    admin=clients(monkeypatch)
    alice,a=create_user(admin,'result-alice@example.test')
    bob,b=create_user(admin,'result-bob@example.test')
    observer,o=create_user(admin,'result-observer@example.test','observer')
    batch=create_batch(a,'Alice result')
    _,original,_=seed_photo(batch,alice)
    run,_=seed_result(batch,alice,original)
    with database.connect() as db:
        db.execute("UPDATE jobs SET snapshot=snapshot || %s,started_at=now()-interval '66 seconds',finished_at=now() WHERE id=%s",
                   (Jsonb({'models':{'megaloc':{'processed':188,'groups':27,'uncertain':0}},
                           'progress':{'overall_percent':100}}),run))
    own=a.get('/api/results/catalog')
    assert own.status_code==200,own.text
    card=own.json()['items'][0]
    owner_card=admin.get('/api/results/catalog?search=Alice').json()['items'][0]
    for key,value in {'photo_count':188,'groups':27,'uncertain':0,'overall_percent':100}.items():
        assert card[key]==owner_card[key]==value
    assert card['id']==run and card['can_open'] and card['can_zip'] and card['can_history']
    assert b.get('/api/results/catalog').json()['items']==[]
    assert b.get('/api/results/'+run).status_code==404
    assert o.get('/api/results/catalog').json()['items']==[]
    assert admin.put(f'/api/admin/users/{observer}/grants',json={'run_ids':[run]}).status_code==200
    granted=o.get('/api/results/catalog').json()['items'][0]
    assert granted['id']==run and granted['groups']==27
    assert granted['thumbnail_url'] is None and not granted['can_history']
    assert 'batch_id' not in granted and 'owner_id' not in granted
    assert a.get('/api/results/catalog?search=nonexistent').json()['items']==[]
    assert admin.put(f'/api/admin/accounts/{alice}',json={'display_name':'Alice','role_id':'employee',
        'overrides':{'results.media':'none','results.zip':'none','queue.detail':'none'}}).status_code==200
    denied=a.get('/api/results/catalog').json()['items'][0]
    assert not denied['can_media'] and not denied['can_zip'] and not denied['can_history']
    assert denied['thumbnail_url'] is None
    assert a.get('/api/download/'+run).status_code in (403,404)


def test_account_creation_quota_atomic_and_exact(system,monkeypatch):
    from server.services import disk_guard
    admin=clients(monkeypatch)
    gib=1024**3
    monkeypatch.setattr(disk_guard,'stat',lambda path:(100*gib,80*gib))
    def create(name,quota):
        return admin.post('/api/admin/users',json={'email':name,'password':PASSWORD,
            'confirmation':PASSWORD,'role_id':'employee','run_ids':[],'storage_limit_bytes':quota})
    for i,quota in enumerate((20*gib,gib//2,0,None)):
        name=f'quota{i}@example.test'
        response=create(name,quota)
        assert response.status_code==201,response.text
        with database.connect() as db:
            assert db.execute("SELECT storage_limit_bytes FROM users WHERE username=%s",(name,)).fetchone()['storage_limit_bytes']==quota
    for i,quota in enumerate((-1,0.5,'20',101*gib)):
        name=f'badquota{i}@example.test'
        response=create(name,quota)
        assert response.status_code==422,response.text
        with database.connect() as db:
            assert db.execute("SELECT id FROM users WHERE username=%s",(name,)).fetchone() is None
    assert create('quota0@example.test',gib).status_code==409


def test_delete_account_cancels_fifo_before_exclusive_lease_and_preserves_other_owner(system,monkeypatch):
    from server.db.repositories import work_queue
    from server.services import operations
    from server.services.account_activity import lease
    admin=clients(monkeypatch)
    alice,a=create_user(admin,'delete-active@example.test')
    bob,b=create_user(admin,'delete-other@example.test')
    batches=[create_batch(a,'Running'),create_batch(a,'Queued'),create_batch(b,'Other')]
    files=[seed_photo(batch,owner)[1] for batch,owner in zip(batches,(alice,alice,bob))]
    runs=['20261126T180000-'+uuid.uuid4().hex[:12] for _ in batches]
    with database.connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(%s)",(work_queue.LOCK,))
        for batch,run in zip(batches,runs):
            db.execute("INSERT INTO jobs(id,batch_id,status,snapshot) VALUES(%s,%s,'queued',%s)",
                       (run,batch,Jsonb({'id':run,'status':'queued'})))
            work_queue.insert_fo(db,run)
        db.execute("UPDATE jobs SET status='running',started_at=now() WHERE id=%s",(runs[0],))
        db.execute("UPDATE work_queue SET state='running',started_at=now() WHERE fo_run_id=%s",(runs[0],))
    token=operations.start(batches[0],'download')
    endpoint=f'/api/admin/accounts/{alice}/lifecycle'
    with lease() as allowed:
        assert allowed
        reply=admin.post(endpoint,json={'operation':'delete','confirmation':'delete-active@example.test'})
        assert reply.status_code==202,reply.text
        account_lifecycle.run_pending()  # cannot acquire exclusive lease
        assert a.get('/api/auth/me').status_code==401
        with database.connect() as db:
            states={r['id']:r['status'] for r in db.execute("SELECT id,status FROM jobs")}
            assert states==dict(zip(runs,('stopping','stopped','queued')))
            assert db.execute("SELECT state FROM work_queue WHERE fo_run_id=%s",(runs[1],)).fetchone()['state']=='stopped'
        assert cleanup.cleanup_one(batches[0])=='waiting'
        assert all(path.is_file() for path in files)
    with database.connect() as db:
        db.execute("UPDATE jobs SET status='stopped',finished_at=now() WHERE id=%s",(runs[0],))
        work_queue.finish_fo(db,runs[0],'stopped')
    assert cleanup.cleanup_one(batches[0])=='waiting'
    operations.finish(token)
    for batch in batches[:2]:assert cleanup.cleanup_one(batch)=='completed'
    settle()
    with database.connect() as db:db.execute("UPDATE account_lifecycle SET next_attempt=now() WHERE source_id=%s",(alice,))
    account_lifecycle.run_pending()
    assert admin.get(endpoint).status_code==404
    assert not files[0].exists() and not files[1].exists() and files[2].is_file()
    assert b.get('/api/batches/'+str(batches[2])).status_code==200
    with database.connect() as db:
        assert not db.execute("SELECT 1 FROM users WHERE id=%s",(alice,)).fetchone()
        assert not db.execute("SELECT 1 FROM storage_files WHERE owner_id=%s",(alice,)).fetchone()
        assert not db.execute("SELECT 1 FROM storage_reservations WHERE owner_id=%s",(alice,)).fetchone()
        assert db.execute("SELECT state FROM work_queue WHERE fo_run_id=%s",(runs[2],)).fetchone()['state']=='queued'


def test_reference_import_sessions_are_not_shared_by_client_uuid(system,monkeypatch):
    from .test_unified_queue_stage3 import add_published_reference
    import hashlib
    add_published_reference(system)
    admin=clients(monkeypatch)
    alice,a=create_user(admin,'import-alice@example.test',overrides={'references.import':'all'})
    bob,b=create_user(admin,'import-bob@example.test',overrides={'references.import':'all'})
    session=str(uuid.uuid4());file_id=str(uuid.uuid4())
    path='/api/reference-imports';url=path+'/'+session
    assert a.post(path,json={'client_session_id':session}).status_code==201
    assert a.post(path,json={'client_session_id':session}).status_code==201
    raw=_jpg()
    manifest={'files':[{'upload_id':file_id,'sam':'SAM 0001','relative_path':'SAM 0001/private-name.jpg',
        'filename':'private-name.jpg','size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}]}
    response=a.put(url+'/manifest',json=manifest)
    assert response.status_code==200,response.text
    assert a.get(url).status_code==200
    assert 'private-name.jpg' in a.get(url).text
    assert b.get(path).json()=={'sessions':[],'total':0}
    assert admin.get(path).json()['total']==1
    assert b.post(path,json={'client_session_id':session}).status_code==404
    assert b.get(url).status_code==404
    assert b.put(url+'/manifest',json=manifest).status_code==404
    file=url+'/files/'+file_id
    assert b.get(file).status_code==404
    assert b.patch(file,content=raw,headers={'Upload-Offset':'0'}).status_code==404
    assert b.post(file+'/finish').status_code==404
    assert b.post(file+'/duplicate',json={'sha256':hashlib.sha256(raw).hexdigest()}).status_code==404
    assert b.post(url+'/complete').status_code==404
    assert a.get(file).json()['received']==0
    assert b.get('/api/references').status_code==200
    with database.connect() as db:
        assert db.execute("SELECT requested_by FROM reference_import_sessions WHERE id=%s",(session,)).fetchone()['requested_by']==alice
