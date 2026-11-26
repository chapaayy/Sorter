"""Session login/logout; preserve existing cookie/origin/auth behavior."""
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field
from ...auth import check_origin,login,logout,COOKIE_NAME,SESSION_DAYS

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
    response.set_cookie(COOKIE_NAME,token,max_age=SESSION_DAYS*24*3600,secure=True,
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
    user=request.state.user
    # Existing observer API clients retain their original response shape.
    return {"username":user["username"],"permissions":user["permissions"],"role_id":user["role_id"]} if user.get("role_id") not in (None,"observer","owner") or (user.get("role_id")=="observer" and user.get("permissions")!={k:"granted" for k in ("results.view","results.media","results.zip")}) else {"username":user["username"]}

@router.get("/profile")
def profile(request:Request):
    user=request.state.user
    return {"username":user["username"],"display_name":user.get("display_name"),"role_id":user.get("role_id"),"permissions":user.get("permissions",{})}

@router.get("/storage")
def own_storage(request:Request):
    from ...services.storage_admin import account_detail
    data=account_detail(request.state.user["id"],limit=1)
    return {"account":data["account"],"categories":data["categories"],"sampled_at":data["sampled_at"]}
