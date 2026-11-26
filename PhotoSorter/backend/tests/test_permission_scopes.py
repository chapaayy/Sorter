import pytest
from server.security.scopes import allowed_for, covers, may_delegate

@pytest.mark.parametrize('scope,own,granted,expected', [
    ('none', True, True, False), ('own', True, False, True),
    ('own', False, True, False), ('granted', True, False, False),
    ('granted', False, True, True), ('all', False, False, True),
])
def test_object_access(scope,own,granted,expected):
    assert allowed_for(scope,own=own,granted=granted) is expected

@pytest.mark.parametrize('have,want,expected', [
    ('own','all',False),('own','granted',False),('all','own',True),
    ('granted','granted',False),('none','none',True),('all','granted',True),
])
def test_scope_ceiling(have,want,expected):
    assert covers(have,want) is expected

@pytest.mark.parametrize('key,have,want,expected', [
    ('accounts.password','all','all',False),('storage.configure','all','all',False),
    ('system.update','all','all',False),('system.models','all','all',True),
    ('photos.upload','own','all',False),('photos.upload','own','own',True),
    ('photos.upload','all','none',True),('accounts.password','all','none',True),
])
def test_delegation(key,have,want,expected):
    assert may_delegate(key,have,want) is expected
