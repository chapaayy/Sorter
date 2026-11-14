"""Session login/logout; preserve existing cookie/origin/auth behavior."""
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field
from ...auth import check_origin,login,logout,COOKIE_NAME

router=APIRouter(prefix="/api/auth",tags=["auth"])
class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=254)
    password:str=Field(min_length=1,max_length=256)

@router.post("/login")
def sign_in(credentials:Credentials,request:Request):
    check_origin(request)
    token=login(credentials.username,credentials.password,request.client.host if request.client else 'unknown')
    username = credentials.username.strip()
    response=JSONResponse({"username":username.lower() if '@' in username else username})
    response.set_cookie(COOKIE_NAME,token,max_age=7*24*3600,secure=True,
                        httponly=True,samesite="strict",path="/")
    return response

@router.post("/logout")
def sign_out(request:Request):
    logout(request)
    response=JSONResponse({"ok":True})
    response.delete_cookie(COOKIE_NAME,path="/")
    return response

@router.get("/me")
def me(request:Request):
    return {"username":request.state.user["username"]}
