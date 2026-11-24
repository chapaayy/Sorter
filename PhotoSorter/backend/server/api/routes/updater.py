"""Owner-only proxy to a fixed-command Unix socket; no shell or Docker access."""
import json
import socket
from fastapi import APIRouter,HTTPException,Request
from ...security.access_policy import is_owner

router=APIRouter(prefix="/api/system/update",tags=["update"])
SOCKET="/run/map-updater-rpc/control.sock"

def request_host(request,command):
    user=getattr(request.state,"user",None)
    if not user or not is_owner(user):
        raise HTTPException(403,"Недостаточно прав")
    if command not in ("status","check","update"):
        raise ValueError("Unknown updater command")
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(4)
            sock.connect(SOCKET)
            sock.sendall((command+"\n").encode("ascii"))
            with sock.makefile("rb") as stream:
                result=json.loads(stream.readline(65536))
    except (OSError,ValueError):
        if command=="status":
            return {"available":False,"detail":"Служба обновления недоступна"}
        raise HTTPException(503,"Служба обновления недоступна")
    if not isinstance(result,dict):
        raise HTTPException(503,"Неверный ответ обновлятора")
    if result.get("rejected"):
        raise HTTPException(409,result.get("detail","Обновление недоступно"))
    return result

@router.get("")
def status(request:Request):
    return request_host(request,"status")

@router.post("/check")
def check(request:Request):
    return request_host(request,"check")

@router.post("/start")
def start(request:Request):
    return request_host(request,"update")
