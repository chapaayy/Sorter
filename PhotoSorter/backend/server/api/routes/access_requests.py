"""Public submission and owner-only application inbox."""
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, SecretStr, StrictBool
from ... import auth
from ...security.access_policy import RUN
from ...security.login_throttle import LoginThrottle
from ...services import access_requests

router = APIRouter(prefix="/api", tags=["access-requests"])
submissions = LoginThrottle()


class Application(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=12, max_length=256)
    confirmation: SecretStr = Field(min_length=1, max_length=256)
    comment: str = Field(min_length=1, max_length=1500)


class Grants(BaseModel):
    run_ids: list[Annotated[str, Field(pattern=f"^{RUN}$", max_length=28)]] = Field(max_length=100)


class Decision(Grants):
    approved: StrictBool
    run_ids: list[Annotated[str, Field(pattern=f"^{RUN}$", max_length=28)]] = Field(default_factory=list, max_length=100)


@router.post("/auth/register", status_code=202)
def register(payload: Application, request: Request):
    auth.check_origin(request)
    client = request.client.host if request.client else "unknown"
    key = payload.email.strip().lower()
    if not submissions.take(key, client):
        raise HTTPException(429, "Слишком много заявок. Попробуйте позже.")
    access_requests.submit(key, payload.password.get_secret_value(),
                           payload.confirmation.get_secret_value(), payload.comment)
    # Do not disclose whether an application or account already exists.
    return {"status": "received"}


@router.get("/admin/access-requests")
def inbox(status: Literal["pending", "approved", "rejected"] = "pending",
          limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    return access_requests.page(status, limit, offset)


@router.post("/admin/access-requests/{request_id}/decision")
def moderate(request_id: UUID, decision: Decision):
    return access_requests.decide(request_id, decision.approved, decision.run_ids)


@router.get("/admin/access-requests/{request_id}/grants")
def read_grants(request_id: UUID):
    return access_requests.grants(request_id)


@router.put("/admin/access-requests/{request_id}/grants")
def update_grants(request_id: UUID, payload: Grants):
    return access_requests.grants(request_id, payload.run_ids)
