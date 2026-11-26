"""Owner-only management of roles and account security; no generic command endpoint."""
from typing import Literal,Annotated
from uuid import UUID
from fastapi import APIRouter,HTTPException,Request,Query,Path
from pydantic import BaseModel,Field,SecretStr,StrictBool
from ...security.access_policy import is_owner
from ...security.roles import has
from ...services import accounts

router=APIRouter(prefix="/api/admin/accounts",tags=["accounts"])

def actor(request):
    user=getattr(request.state,"user",None)
    if not user:raise HTTPException(403,"Недостаточно прав")
    return user["username"]

class Role(BaseModel):
    name:str=Field(min_length=1,max_length=100)
    description:str=Field(default="",max_length=500)
    permissions:dict[str,str]=Field(default_factory=dict,max_length=100)

class Edit(BaseModel):
    display_name:str=Field(max_length=120)
    role_id:str=Field(min_length=1,max_length=64)
    overrides:dict[str,str]=Field(default_factory=dict,max_length=100)

class Security(BaseModel):
    action:Literal["block","unblock","reset_password","revoke_all","revoke_session"]
    confirmed:StrictBool
    password:SecretStr|None=None
    session_id:UUID|None=None

class Registration(BaseModel):
    enabled:StrictBool

class DeleteRole(BaseModel):
    confirmed:StrictBool
    replacement:str|None=None

@router.get("")
def list_accounts(request:Request,search:str=Query("",max_length=120),limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0)):
    actor(request)
    return accounts.list_accounts(search,limit,offset,include_storage=has(request.state.user,"accounts.storage"))

@router.get("/roles")
def roles(request:Request):
    actor(request);return accounts.roles()

@router.post("/roles",status_code=201)
def create_role(request:Request,payload:Role):
    return accounts.save_role(actor(request),None,payload.name.strip(),payload.description,payload.permissions)

@router.put("/roles/{role_id}")
def edit_role(request:Request,role_id:str,payload:Role):
    return accounts.save_role(actor(request),role_id,payload.name.strip(),payload.description,payload.permissions)

@router.post("/roles/{role_id}/delete")
def delete_role(request:Request,role_id:str,payload:DeleteRole):
    who=actor(request)
    if not payload.confirmed:raise HTTPException(422,"Требуется подтверждение")
    return accounts.delete_role(who,role_id,payload.replacement)

@router.get("/registration")
def registration(request:Request):
    actor(request);return accounts.registration()

@router.put("/registration")
def edit_registration(request:Request,payload:Registration):
    return accounts.registration(payload.enabled,actor(request))

@router.get("/events")
def events(request:Request,offset:int=Query(0,ge=0)):
    actor(request);return accounts.events(offset)

@router.get("/{user_id}")
def detail(request:Request,user_id:Annotated[int,Path(gt=0,le=2**63-1)]):
    actor(request);return accounts.detail(user_id,include_sessions=has(request.state.user,"accounts.sessions"))

@router.put("/{user_id}")
def edit(request:Request,user_id:Annotated[int,Path(gt=0,le=2**63-1)],payload:Edit):
    return accounts.edit(actor(request),user_id,payload.display_name,payload.role_id,payload.overrides)

@router.post("/{user_id}/security")
def security(request:Request,user_id:Annotated[int,Path(gt=0,le=2**63-1)],payload:Security):
    who=actor(request)
    if not payload.confirmed:raise HTTPException(422,"Требуется подтверждение")
    return accounts.security(who,user_id,payload.action,payload.password.get_secret_value() if payload.password else None,payload.session_id)

class Lifecycle(BaseModel):
    operation:Literal["transfer","transfer_delete","delete"]
    recipient_id:Annotated[int,Field(gt=0,le=2**63-1)]|None=None
    confirmation:str=Field(min_length=1,max_length=254)

@router.get("/{user_id}/lifecycle")
def lifecycle_preview(request:Request,user_id:Annotated[int,Path(gt=0,le=2**63-1)]):
    actor(request)
    from ...security.route_permissions import require
    require(request.state.user,"accounts.storage")
    from ...services import account_lifecycle
    return account_lifecycle.preview(user_id)

@router.post("/{user_id}/lifecycle",status_code=202)
def lifecycle(request:Request,user_id:Annotated[int,Path(gt=0,le=2**63-1)],payload:Lifecycle):
    from ...services import account_lifecycle
    return account_lifecycle.request(actor(request),user_id,payload.operation,payload.recipient_id,payload.confirmation)
