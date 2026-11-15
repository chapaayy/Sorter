"""Owner-only creation and listing of viewer accounts."""
from typing import Annotated

from fastapi import APIRouter, Path, Query
from pydantic import Field, SecretStr

from ...services import admin_users
from .access_requests import Grants

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])
UserId = Annotated[int, Path(gt=0, le=9223372036854775807)]


class NewUser(Grants):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=12, max_length=256)
    confirmation: SecretStr = Field(min_length=1, max_length=256)


@router.get("")
def users(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    return admin_users.list_users(limit, offset)


@router.post("", status_code=201)
def create(payload: NewUser):
    return admin_users.create(payload.email, payload.password.get_secret_value(),
                              payload.confirmation.get_secret_value(), payload.run_ids)


@router.get("/{user_id}/grants")
def read_grants(user_id: UserId):
    return admin_users.grants(user_id)


@router.put("/{user_id}/grants")
def update_grants(user_id: UserId, payload: Grants):
    return admin_users.grants(user_id, payload.run_ids)
