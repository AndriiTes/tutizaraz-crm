"""
Проста автентифікація на одного адміністратора (без БД-користувачів),
достатня для старту. SECRET_KEY і ADMIN_PASSWORD задаються в Render
як змінні середовища — ніколи не зберігати їх у коді.
"""
import base64
import hashlib
import hmac
import os
import time

from fastapi import Header, HTTPException, status

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-key-change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # токен живе 7 днів


def create_token() -> str:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    signature = hmac.new(SECRET_KEY.encode(), str(expires_at).encode(), hashlib.sha256).hexdigest()
    raw = f"{expires_at}.{signature}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_token(token: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        expires_at_str, signature = raw.split(".", 1)
        expected = hmac.new(SECRET_KEY.encode(), expires_at_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        return int(expires_at_str) >= int(time.time())
    except Exception:
        return False


def require_auth(authorization: str = Header(default="")) -> bool:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизовано")
    token = authorization.removeprefix("Bearer ").strip()
    if not verify_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен недійсний або прострочений")
    return True
