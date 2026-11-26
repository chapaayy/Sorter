import pytest
from fastapi import HTTPException
from server.security.roles import effective,validate,result_allowed,LEGACY
from server.security.access_policy import authorize,require_published

RUN='20261114T170000-0123456789ab'
def user(role,overrides=None):
    return {'id':7,'username':'viewer@example.test','access_role':'viewer','permissions':effective(role,overrides or {})}

@pytest.mark.parametrize('scope,own,granted,expected',[
    ('none',True,True,False),('own',True,False,True),('own',False,True,False),
    ('all',False,False,True),('granted',False,True,True),('granted',True,False,False),
])
def test_object_scopes(scope,own,granted,expected):
    u=user({'results.view':scope,'results.zip':'all'})
    assert result_allowed(u,'results.zip',own=own,granted=granted)==expected

def test_override_denial_and_role_change():
    role={'results.view':'all','results.zip':'all'}
    assert not result_allowed(user(role,{'results.zip':'none'}),'results.zip',own=True,granted=True)
    role['results.view']='none'
    assert not result_allowed(user(role),'results.zip',own=True,granted=True)
    assert effective({}, {}) and all(v=='none' for v in effective({}, {}).values())

def test_default_deny_routes_and_owner():
    u=user(LEGACY)
    authorize(u,'GET','/api/results/'+RUN)
    for method,path in [('POST','/api/batches'),('GET','/api/admin/accounts'),('GET','/api/photos/secret/original'),('GET','/api/results/'+RUN+'/megaloc')]:
        with pytest.raises(HTTPException) as err:authorize(u,method,path)
        assert err.value.status_code==403
    authorize({'username':'admin','access_role':'owner'},'GET','/api/admin/accounts')
    with pytest.raises(HTTPException):authorize(user(LEGACY,{'results.zip':'none'}),'GET','/api/download/'+RUN)

def test_unknown_permissions_rejected():
    for value in ({'admin.owner':'all'},{'results.view':'root'}):
        with pytest.raises(HTTPException):validate(value)

def test_object_access_does_not_use_id_as_permission():
    class DB:
        def execute(self,sql,args):
            assert args==(7,RUN)
            return self
        def fetchone(self):return {'owner_id':8,'granted':False,'display_name':'hidden','status':'completed'}
    with pytest.raises(HTTPException) as err:require_published(DB(),RUN,7,user({'results.view':'own'}))
    assert err.value.status_code==404
    assert require_published(DB(),RUN,7,user({'results.view':'all'}))['can_zip'] is False
