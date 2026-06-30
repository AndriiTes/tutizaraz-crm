from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter()


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
    # TODO: розпарсити update від Telegram Bot API,
    # створити models.Order(source="telegram", ...)
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
