from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel


class Customer(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    comment: Optional[str] = None


class OrderItemIn(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    qty: Optional[int] = None
    price: Optional[float] = None


class WebsiteOrderIn(BaseModel):
    """Формат, який надсилає форма сайту (script.js -> CONFIG.WEBHOOK_URL)."""
    source: Optional[str] = "website"
    customer: Customer
    items: List[OrderItemIn] = []
    total: Optional[float] = 0
    createdAt: Optional[str] = None


class WebsiteChatIn(BaseModel):
    """Формат повідомлення з плаваючого чат-віджета на сайті."""
    source: Optional[str] = "website-chat"
    name: Optional[str] = None
    message: str
    createdAt: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    source: str
    status: str
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    comment: Optional[str] = None
    external_id: Optional[str] = None
    items: Optional[Any] = None
    total: float
    created_at: datetime

    class Config:
        from_attributes = True


class StatusUpdate(BaseModel):
    status: str


class LoginIn(BaseModel):
    password: str


class LoginOut(BaseModel):
    token: str
