import os

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
VIBER_BOT_TOKEN = os.getenv("VIBER_BOT_TOKEN", "")
PUBLIC_BACKEND_URL = os.getenv("PUBLIC_BACKEND_URL", "https://tutizaraz-crm.onrender.com")

# Спільний для WhatsApp і Instagram, обидва йдуть через Meta Graph API
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
META_GRAPH_VERSION = "v20.0"

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")


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
    event = body.get("event")

    if event != "message":
        # Інші типи подій від Viber (підписка, доставлено, прочитано тощо) —
        # просто підтверджуємо отримання, заявку не створюємо
        return {"status": 0}

    sender = body.get("sender", {})
    message = body.get("message", {})
    text = message.get("text", "")

    order = models.Order(
        source="viber",
        status="new",
        name=sender.get("name") or "Viber користувач",
        comment=text,
        external_id=sender.get("id"),
        raw_payload=body,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    if VIBER_BOT_TOKEN and sender.get("id"):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    "https://chatapi.viber.com/pa/send_message",
                    headers={"X-Viber-Auth-Token": VIBER_BOT_TOKEN},
                    json={
                        "receiver": sender.get("id"),
                        "type": "text",
                        "sender": {"name": "Тут&Зараз"},
                        "text": "Дякуємо за звернення! Ми вже бачимо ваше повідомлення і скоро зв'яжемось з вами. 🍔",
                    },
                )
        except Exception:
            pass

    return {"status": 0}


@router.get("/admin/setup-viber-webhook")
async def setup_viber_webhook():
    """
    Одноразовий виклик: реєструє наш /webhooks/viber у Viber.
    Достатньо відкрити цю адресу в браузері один раз, коли
    VIBER_BOT_TOKEN вже заданий у змінних середовища Render.
    """
    if not VIBER_BOT_TOKEN:
        return {"ok": False, "error": "VIBER_BOT_TOKEN не заданий у змінних середовища Render"}

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(
            "https://chatapi.viber.com/pa/set_webhook",
            headers={"X-Viber-Auth-Token": VIBER_BOT_TOKEN},
            json={
                "url": f"{PUBLIC_BACKEND_URL}/webhooks/viber",
                "event_types": ["message", "subscribed", "unsubscribed"],
            },
        )
    return res.json()


def _verify_meta_webhook(request: Request) -> PlainTextResponse:
    """Спільна логіка верифікації для WhatsApp і Instagram — обидва йдуть через Meta."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if mode == "subscribe" and META_VERIFY_TOKEN and token == META_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    return PlainTextResponse("Verification failed", status_code=403)


@router.get("/webhooks/whatsapp")
async def verify_whatsapp(request: Request):
    return _verify_meta_webhook(request)


@router.post("/webhooks/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    try:
        value = body["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            # Статус-апдейти (доставлено/прочитано) — заявку не створюємо
            return {"ok": True}

        message = messages[0]
        from_number = message.get("from")
        text = message.get("text", {}).get("body", "")

        contacts = value.get("contacts", [])
        name = contacts[0].get("profile", {}).get("name") if contacts else None

        order = models.Order(
            source="whatsapp",
            status="new",
            name=name or "WhatsApp користувач",
            phone=from_number,
            comment=text,
            external_id=from_number,
            raw_payload=body,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        if WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID and from_number:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        f"https://graph.facebook.com/{META_GRAPH_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages",
                        headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
                        json={
                            "messaging_product": "whatsapp",
                            "to": from_number,
                            "text": {
                                "body": "Дякуємо за звернення! Ми вже бачимо ваше повідомлення і скоро зв'яжемось з вами. 🍔"
                            },
                        },
                    )
            except Exception:
                pass
    except (KeyError, IndexError, TypeError):
        # Неочікувана структура апдейту (статуси, помилки тощо) — просто ігноруємо
        pass

    return {"ok": True}


@router.get("/webhooks/instagram")
async def verify_instagram(request: Request):
    return _verify_meta_webhook(request)


@router.post("/webhooks/instagram")
async def instagram_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    try:
        messaging_event = body["entry"][0]["messaging"][0]
        message = messaging_event.get("message", {})
        sender_id = messaging_event.get("sender", {}).get("id")

        if not sender_id or message.get("is_echo"):
            # is_echo — це наше ж власне надіслане повідомлення, що повернулось вебхуком
            return {"ok": True}

        text = message.get("text", "")

        order = models.Order(
            source="instagram",
            status="new",
            name="Instagram користувач",
            comment=text,
            external_id=sender_id,
            raw_payload=body,
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        if INSTAGRAM_ACCESS_TOKEN:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        f"https://graph.facebook.com/{META_GRAPH_VERSION}/me/messages",
                        params={"access_token": INSTAGRAM_ACCESS_TOKEN},
                        json={
                            "recipient": {"id": sender_id},
                            "message": {
                                "text": "Дякуємо за звернення! Ми вже бачимо ваше повідомлення і скоро зв'яжемось з вами. 🍔"
                            },
                        },
                    )
            except Exception:
                pass
    except (KeyError, IndexError, TypeError):
        pass

    return {"ok": True}


@router.post("/webhooks/telephony")
async def telephony_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Різні провайдери телефонії (Zadarma, Binotel, Ringostat тощо) шлють
    вебхуки в різних форматах: хтось JSON, хтось form-urlencoded, і назви
    полів для номера телефону теж відрізняються. Тому беремо дані максимально
    гнучко і пробуємо найпоширеніші назви полів. Сирий вміст завжди зберігаємо
    в raw_payload — якщо щось не розпізналось автоматично, його видно в CRM
    і можна буде доточити обробку під конкретного провайдера.
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    if not isinstance(data, dict):
        data = {"raw": str(data)}

    phone = (
        data.get("caller_id")
        or data.get("from")
        or data.get("phone")
        or data.get("ani")
        or data.get("src")
        or data.get("CallerIDNum")
        or data.get("caller_number")
    )
    event = data.get("event") or data.get("disposition") or data.get("call_status") or "call"

    order = models.Order(
        source="phone",
        status="new",
        phone=str(phone) if phone else None,
        comment=f"Подія телефонії: {event}",
        external_id=str(phone) if phone else None,
        raw_payload=data,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return {"ok": True}
