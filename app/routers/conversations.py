from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_auth
from ..database import get_db
from .webhooks import save_message, send_channel_reply

router = APIRouter()


@router.get("/api/conversations", response_model=List[schemas.ConversationOut])
def list_conversations(db: Session = Depends(get_db), _auth: bool = Depends(require_auth)):
    """
    Список розмов — по одній картці на пару (channel, external_id),
    з прев'ю останнього повідомлення. Найновіші розмови зверху.
    Розмова вважається непрочитаною, якщо останнє повідомлення в ній — вхідне.
    """
    last_at_subq = (
        db.query(
            models.Message.channel,
            models.Message.external_id,
            func.max(models.Message.created_at).label("last_at"),
        )
        .group_by(models.Message.channel, models.Message.external_id)
        .subquery()
    )

    rows = (
        db.query(models.Message)
        .join(
            last_at_subq,
            (models.Message.channel == last_at_subq.c.channel)
            & (models.Message.external_id == last_at_subq.c.external_id)
            & (models.Message.created_at == last_at_subq.c.last_at),
        )
        .order_by(models.Message.created_at.desc())
        .all()
    )

    return [
        schemas.ConversationOut(
            channel=m.channel,
            external_id=m.external_id,
            customer_name=m.customer_name,
            last_message=m.body,
            last_at=m.created_at,
            unread=(m.direction == "in"),
        )
        for m in rows
    ]


@router.get("/api/conversations/{channel}/{external_id}", response_model=List[schemas.MessageOut])
def get_conversation(channel: str, external_id: str, db: Session = Depends(get_db),
                      _auth: bool = Depends(require_auth)):
    rows = (
        db.query(models.Message)
        .filter(models.Message.channel == channel, models.Message.external_id == external_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Розмову не знайдено")
    return rows


@router.post("/api/conversations/{channel}/{external_id}/reply", response_model=schemas.MessageOut)
async def reply_to_conversation(channel: str, external_id: str, data: schemas.ReplyIn,
                                 db: Session = Depends(get_db), _auth: bool = Depends(require_auth)):
    """
    Відповідь оператора з CRM-панелі. Для Telegram/Viber/WhatsApp/Instagram
    реально надсилає повідомлення через API каналу. Для website-chat просто
    зберігає — віджет сайту підхопить це повідомлення сам через опитування.
    """
    ok = await send_channel_reply(channel, external_id, data.text)
    if not ok and channel != "website-chat":
        raise HTTPException(
            status_code=502,
            detail="Не вдалось надіслати повідомлення в канал — перевірте, чи задано токен у змінних середовища",
        )

    existing = (
        db.query(models.Message)
        .filter(models.Message.channel == channel, models.Message.external_id == external_id)
        .order_by(models.Message.created_at.desc())
        .first()
    )
    customer_name = existing.customer_name if existing else None

    msg = save_message(db, channel=channel, external_id=external_id, customer_name=customer_name,
                        direction="out", body=data.text)
    return msg
