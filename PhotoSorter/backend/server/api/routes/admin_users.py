"""Owner-only creation and listing of viewer accounts."""
from typing import Annotated

from fastapi import APIRouter, Path, Query,Request
from pydantic import Field, SecretStr, StrictInt

from ...services import admin_users
from .access_requests import Grants

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])
UserId = Annotated[int, Path(gt=0, le=9223372036854775807)]


class NewUser(Grants):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=12, max_length=256)
    confirmation: SecretStr = Field(min_length=1, max_length=256)
    role_id:str=Field(default='observer',max_length=64)
    display_name:str=Field(default='',max_length=120)
    storage_limit_bytes:StrictInt|None=Field(default=None,ge=0,le=2**63-1)
    overrides:dict[str,str]=Field(default_factory=dict,max_length=100)


@router.get("")
def users(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    return admin_users.list_users(limit, offset)


@router.post("", status_code=201)
def create(payload: NewUser,request:Request):
    return admin_users.create(payload.email, payload.password.get_secret_value(),
                              payload.confirmation.get_secret_value(), payload.run_ids,role_id=payload.role_id,display_name=payload.display_name,
                              storage_limit_bytes=payload.storage_limit_bytes,overrides=payload.overrides,actor=request.state.user['username'])


@router.get("/{user_id}/grants")
def read_grants(user_id: UserId,request:Request):
    return admin_users.grants(user_id,actor=request.state.user['username'])


@router.put("/{user_id}/grants")
def update_grants(user_id: UserId, payload: Grants,request:Request):
    return admin_users.grants(user_id, payload.run_ids,actor=request.state.user['username'])
