import os

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


@router.post("/webhooks/website-order")
async def website_order(payload: schemas.WebsiteOrderIn, db: Session = Depends(get_db)):
    """
    Приймає заявку з форми сайту (script.js -> CONFIG.WEBHOOK_URL).
    Очікуваний формат тіла запиту вже узгоджений з фронтендом сайту.
    """
    order = models.Order(
        source=payload.source or "website",
        status="new",
        name=payload.customer.name,
        phone=payload.customer.phone,
        address=payload.customer.address,
        comment=payload.customer.comment,
        items=[item.model_dump() for item in payload.items],
        total=payload.total or 0,
        raw_payload=payload.model_dump(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"ok": True, "order_id": order.id}


# ---------------------------------------------------------------------------
# Заготовки під наступні канали. Ендпоінти вже існують і повертають 200 OK,
# щоб їх можна було одразу прописати в налаштуваннях ботів — саму логіку
# розбору повідомлень додамо на кроках 4–5 нашого плану, коли будуть токени.
# ---------------------------------------------------------------------------

@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    message = body.get("message") or body.get("edited_message")
    if not message:
        # Telegram шле й інші типи апдейтів (callback_query тощо) — поки ігноруємо
        return {"ok": True}

    chat = message.get("chat", {})
    from_user = message.get("from", {})
    text = message.get("text", "")

    name_parts = [from_user.get("first_name", ""), from_user.get("last_name", "")]
    full_name = " ".join(p for p in name_parts if p).strip() or from_user.get("username") or "Telegram користувач"

    order = models.Order(
        source="telegram",
        status="new",
        name=full_name,
        comment=text,
        external_id=str(chat.get("id")) if chat.get("id") is not None else None,
        raw_payload=body,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    # Автоматичне підтвердження клієнту, що звернення отримано і фіксується в CRM
    if TELEGRAM_BOT_TOKEN and chat.get("id") is not None:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat.get("id"),
                        "text": "Дякуємо за звернення! Ми вже бачимо ваше повідомлення і скоро зв'яжемось з вами. 🍔"
                    },
                )
        except Exception:
            # Не валимо обробку вебхука через тимчасову недоступність Telegram API
            pass

    return {"ok": True}


@router.post("/webhooks/viber")
async def viber_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    # TODO: розпарсити подію від Viber Callback API,
    # створити models.Order(source="viber", ...)
    return {"ok": True}


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    # TODO: розпарсити подію від WhatsApp Cloud API (Meta),
    # створити models.Order(source="whatsapp", ...)
    return {"ok": True}


@router.post("/webhooks/telephony")
async def telephony_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    # TODO: розпарсити подію про дзвінок від провайдера телефонії,
    # створити models.Order(source="phone", ...) або прив'язати до існуючого клієнта
    return {"ok": True}
