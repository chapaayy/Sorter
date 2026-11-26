"""Central allowlist for implemented, independently enforced permissions."""
from fastapi import HTTPException

CATALOG={
    "results.view":{"label":"Просмотр готовых результатов","group":"Результаты"},
    "results.media":{"label":"Просмотр фото и видео результатов","group":"Результаты","requires":"results.view"},
    "results.zip":{"label":"Скачивание ZIP результатов","group":"Результаты","requires":"results.view"},
}
LEVELS=("none","own","all","granted")
LEGACY={key:"granted" for key in CATALOG}

def validate(values):
    if not isinstance(values,dict) or any(k not in CATALOG or v not in LEVELS for k,v in values.items()):
        raise HTTPException(422,"Неизвестное разрешение или уровень доступа")
    return dict(values)

def effective(role,overrides):
    # Missing or future permissions are denied. Explicit none wins.
    return {key:overrides.get(key,role.get(key,"none")) for key in CATALOG}

def level(user,key):
    if not user or user.get("blocked"):return "none"
    # Compatibility for internal legacy callers; authenticated users always
    # carry the resolved effective permissions.
    return (user.get("permissions",LEGACY if user.get("access_role")=="viewer" else {})).get(key,"none")

def allowed_for(scope,*,own,granted):
    return scope=="all" or (scope=="own" and own) or (scope=="granted" and granted)

def result_allowed(user,action,*,own,granted):
    return allowed_for(level(user,"results.view"),own=own,granted=granted) and allowed_for(level(user,action),own=own,granted=granted)
