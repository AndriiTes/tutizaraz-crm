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
    source: Optional[str] = "website"
    customer: Customer
    items: List[OrderItemIn] = []
    total: Optional[float] = 0
    createdAt: Optional[str] = None


class WebsiteChatIn(BaseModel):
    source: Optional[str] = "website-chat"
    session_id: str
    name: Optional[str] = None
    message: str
    createdAt: Optional[str] = None


class MessageOut(BaseModel):
    id: int
    channel: str
    external_id: str
    customer_name: Optional[str] = None
    direction: str
    sender: Optional[str] = "bot"
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    channel: str
    external_id: str
    customer_name: Optional[str] = None
    last_message: str
    last_at: datetime
    unread: bool
    status: Optional[str] = "ai"
    quality_score: Optional[int] = None


class ConversationStateOut(BaseModel):
    id: int
    channel: str
    external_id: str
    customer_name: Optional[str] = None
    status: str
    ai_enabled: bool
    assigned_to: Optional[str] = None
    quality_score: Optional[int] = None
    quality_report: Optional[str] = None

    class Config:
        from_attributes = True


class ReplyIn(BaseModel):
    text: str


class StatusUpdate(BaseModel):
    status: str


class EscalateIn(BaseModel):
    to: str
    note: Optional[str] = None


class PublicationIn(BaseModel):
    channels: List[str]
    text: str
    image_url: Optional[str] = None


class PublicationOut(BaseModel):
    id: int
    channels: List[str]
    text: str
    status: str
    results: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LoginIn(BaseModel):
    password: str


class LoginOut(BaseModel):
    token: str


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
