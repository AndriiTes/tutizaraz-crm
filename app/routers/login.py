from fastapi import APIRouter, HTTPException

from ..auth import ADMIN_PASSWORD, create_token
from ..schemas import LoginIn, LoginOut

router = APIRouter()


@router.post("/api/login", response_model=LoginOut)
def login(data: LoginIn):
    if data.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Невірний пароль")
    return {"token": create_token()}
