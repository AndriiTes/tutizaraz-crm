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

AUTO_REPLY_TEXT = "Дякуємо за звернення! Ми вже бачимо ваше повідомлення і скоро зв'яжемось з вами. 🍔"


async def send_channel_reply(channel: str, external_id: str, text: str) -> bool:
    """
    Єдина точка відправки повідомлення клієнту назад у канал, з якого він писав.
    Використовується і для автоматичного підтвердження одразу після вхідного
    повідомлення, і для ручних відповідей оператора з CRM-панелі.
    Для website-chat відправляти нічого не потрібно — повідомлення просто
    зберігається в базі, а віджет сайту підхоплює його через опитування (polling).
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            if channel == "telegram" and TELEGRAM_BOT_TOKEN:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": external_id, "text": text},
                )
                return True

            if channel == "viber" and VIBER_BOT_TOKEN:
                await client.post(
                    "https://chatapi.viber.com/pa/send_message",
                    headers={"X-Viber-Auth-Token": VIBER_BOT_TOKEN},
                    json={
                        "receiver": external_id,
                        "type": "text",
                        "sender": {"name": "Тут&Зараз"},
                        "text": text,
                    },
                )
                return True

            if channel == "whatsapp" and WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID:
                await client.post(
                    f"https://graph.facebook.com/{META_GRAPH_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages",
                    headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
                    json={"messaging_product": "whatsapp", "to": external_id, "text": {"body": text}},
                )
                return True

            if channel == "instagram" and INSTAGRAM_ACCESS_TOKEN:
                await client.post(
                    f"https://graph.facebook.com/{META_GRAPH_VERSION}/me/messages",
                    params={"access_token": INSTAGRAM_ACCESS_TOKEN},
                    json={"recipient": {"id": external_id}, "message": {"text": text}},
                )
                return True

            if channel == "website-chat":
                # Нічого надсилати назовні не треба — повідомлення вже в базі,
                # віджет сайту підхопить його сам через опитування.
                return True
    except Exception:
        return False

    return False


def save_message(db: Session, channel: str, external_id: str, customer_name: str | None,
                  direction: str, body: str, raw_payload: dict | None = None) -> models.Message:
    msg = models.Message(
        channel=channel,
        external_id=external_id,
        customer_name=customer_name,
        direction=direction,
        body=body,
        raw_payload=raw_payload,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def is_first_message(db: Session, channel: str, external_id: str) -> bool:
    """
    Перевіряє, чи це перше повідомлення в розмові (немає жодного попереднього
    запису — ні вхідного, ні вихідного). Автовідповідь-привітання надсилається
    лише на старті розмови, щоб не дублювалась на кожне наступне повідомлення
    клієнта, навіть якщо оператор уже відповідає вручну.
    """
    exists = (
        db.query(models.Message.id)
        .filter(models.Message.channel == channel, models.Message.external_id == external_id)
        .first()
    )
    return exists is None


@router.post("/webhooks/website-order")
async def website_order(payload: schemas.WebsiteOrderIn, db: Session = Depends(get_db)):
    """
    Приймає заявку з форми сайту (script.js -> CONFIG.WEBHOOK_URL).
    Це структуроване замовлення (товари, сума) — лишається в таблиці "Заявки".
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


@router.post("/webhooks/website-chat")
async def website_chat(payload: schemas.WebsiteChatIn, db: Session = Depends(get_db)):
    """Приймає повідомлення з плаваючого чат-віджета на сайті — потрапляє в Повідомлення."""
    save_message(
        db,
        channel="website-chat",
        external_id=payload.session_id,
        customer_name=payload.name or "Гість із сайту",
        direction="in",
        body=payload.message,
        raw_payload=payload.model_dump(),
    )
    return {"ok": True}


@router.get("/public/website-chat/{session_id}/messages")
async def public_widget_messages(session_id: str, db: Session = Depends(get_db)):
    """
    Публічний (без авторизації) ендпоінт для самого віджета сайту —
    дозволяє відвідувачу побачити відповідь оператора. Віджет опитує
    цей шлях періодично, поки чат-панель відкрита.
    """
    rows = (
        db.query(models.Message)
        .filter(models.Message.channel == "website-chat", models.Message.external_id == session_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    return [
        {"id": m.id, "direction": m.direction, "body": m.body, "created_at": m.created_at.isoformat()}
        for m in rows
    ]


@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    message = body.get("message") or body.get("edited_message")
    if not message:
        return {"ok": True}

    chat = message.get("chat", {})
    from_user = message.get("from", {})
    text = message.get("text", "")
    chat_id = chat.get("id")
    if chat_id is None:
        return {"ok": True}

    name_parts = [from_user.get("first_name", ""), from_user.get("last_name", "")]
    full_name = " ".join(p for p in name_parts if p).strip() or from_user.get("username") or "Telegram користувач"

    first_message = is_first_message(db, "telegram", str(chat_id))

    save_message(db, channel="telegram", external_id=str(chat_id), customer_name=full_name,
                 direction="in", body=text, raw_payload=body)

    if first_message and await send_channel_reply("telegram", str(chat_id), AUTO_REPLY_TEXT):
        save_message(db, channel="telegram", external_id=str(chat_id), customer_name=full_name,
                     direction="out", body=AUTO_REPLY_TEXT)

    return {"ok": True}


@router.post("/webhooks/viber")
async def viber_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    event = body.get("event")

    if event != "message":
        return {"status": 0}

    sender = body.get("sender", {})
    message = body.get("message", {})
    text = message.get("text", "")
    sender_id = sender.get("id")
    name = sender.get("name") or "Viber користувач"

    if sender_id:
        first_message = is_first_message(db, "viber", sender_id)

        save_message(db, channel="viber", external_id=sender_id, customer_name=name,
                     direction="in", body=text, raw_payload=body)

        if first_message and await send_channel_reply("viber", sender_id, AUTO_REPLY_TEXT):
            save_message(db, channel="viber", external_id=sender_id, customer_name=name,
                         direction="out", body=AUTO_REPLY_TEXT)

    return {"status": 0}


@router.get("/admin/setup-viber-webhook")
async def setup_viber_webhook():
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
            return {"ok": True}

        message = messages[0]
        from_number = message.get("from")
        text = message.get("text", {}).get("body", "")

        contacts = value.get("contacts", [])
        name = contacts[0].get("profile", {}).get("name") if contacts else None
        name = name or "WhatsApp користувач"

        if from_number:
            first_message = is_first_message(db, "whatsapp", from_number)

            save_message(db, channel="whatsapp", external_id=from_number, customer_name=name,
                         direction="in", body=text, raw_payload=body)

            if first_message and await send_channel_reply("whatsapp", from_number, AUTO_REPLY_TEXT):
                save_message(db, channel="whatsapp", external_id=from_number, customer_name=name,
                             direction="out", body=AUTO_REPLY_TEXT)
    except (KeyError, IndexError, TypeError):
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
            return {"ok": True}

        text = message.get("text", "")

        first_message = is_first_message(db, "instagram", sender_id)

        save_message(db, channel="instagram", external_id=sender_id, customer_name="Instagram користувач",
                     direction="in", body=text, raw_payload=body)

        if first_message and await send_channel_reply("instagram", sender_id, AUTO_REPLY_TEXT):
            save_message(db, channel="instagram", external_id=sender_id, customer_name="Instagram користувач",
                         direction="out", body=AUTO_REPLY_TEXT)
    except (KeyError, IndexError, TypeError):
        pass

    return {"ok": True}


@router.post("/webhooks/telephony")
async def telephony_webhook(request: Request, db: Session = Depends(get_db)):
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
