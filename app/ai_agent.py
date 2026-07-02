import json
import os
from typing import Optional

import httpx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AI_MODEL = "claude-sonnet-4-6"

AI_OPERATOR_SYSTEM = """Ти — AI-оператор служби доставки їжі «Тут&Зараз» у Тернополі.
Твоя роль: відповідати на питання клієнтів швидко, ввічливо і по суті.

Що ти знаєш:
- Доставка їжі по Тернополю. Орієнтовний час — 30-40 хвилин.
- Меню: Паста карбонара (189₴), Бургер «Тут&Зараз» (169₴), Піца Маргарита (219₴),
  Картопля фрі (79₴), Цезар (139₴), Лимонад (59₴), Кава американо (49₴), Чізкейк (99₴).
- Приймаємо замовлення через сайт, Telegram, WhatsApp, Instagram, Viber.
- Оплата: готівка або карткою при доставці.
- Зона доставки: Тернопіль.

Як відповідати:
- Коротко і по суті (2-4 речення).
- Мова: українська.
- Тон: дружній.
- Якщо клієнт хоче замовити — допоможи: запитай що саме, адресу, телефон.

ВАЖЛИВО: Відповідай ТІЛЬКИ у форматі JSON:
{
  "can_answer": true/false,
  "response": "текст відповіді якщо can_answer=true, інакше порожній рядок",
  "reason": "якщо can_answer=false — чому"
}

Якщо питання не стосується бізнесу або ти не впевнений — can_answer: false.
Не вигадуй інформацію якої не знаєш."""

AI_QUALITY_SYSTEM = """Ти — AI-контролер якості служби доставки «Тут&Зараз».
Аналізуй завершені розмови між клієнтом і оператором.

Оцінюй по шкалі 1-10:
- Швидкість і якість відповідей
- Ввічливість і тон
- Вирішення проблеми
- Дотримання скрипту продажу

Відповідай ТІЛЬКИ у форматі JSON:
{
  "score": число 1-10,
  "summary": "2-3 речення висновку",
  "strengths": ["що зроблено добре"],
  "improvements": ["що покращити"],
  "operator_feedback": "персональний фідбек оператору"
}"""


async def ai_respond(db, channel: str, external_id: str, customer_name: Optional[str], incoming_text: str) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"can_answer": False, "response": "", "reason": "ANTHROPIC_API_KEY не задано"}

    from app.models import Message
    history = (
        db.query(Message)
        .filter(Message.channel == channel, Message.external_id == external_id)
        .order_by(Message.created_at.desc())
        .limit(10)
        .all()
    )
    history = list(reversed(history))

    messages_payload = []
    for m in history:
        role = "user" if m.direction == "in" else "assistant"
        messages_payload.append({"role": role, "content": m.body})
    messages_payload.append({"role": "user", "content": incoming_text})

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "max_tokens": 500,
                    "system": AI_OPERATOR_SYSTEM,
                    "messages": messages_payload,
                },
            )
        data = res.json()
        raw = data["content"][0]["text"]
        clean = raw.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(clean)
    except Exception as e:
        return {"can_answer": False, "response": "", "reason": str(e)}


async def run_quality_check(db, channel: str, external_id: str) -> dict:
    if not ANTHROPIC_API_KEY:
        return {}

    from app.models import Message, Conversation
    messages = (
        db.query(Message)
        .filter(Message.channel == channel, Message.external_id == external_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    if not messages:
        return {}

    transcript = "\n".join(
        f"[{'Клієнт' if m.direction=='in' else 'Оператор(' + (m.sender or 'bot') + ')'}]: {m.body}"
        for m in messages
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "max_tokens": 800,
                    "system": AI_QUALITY_SYSTEM,
                    "messages": [{"role": "user", "content": f"Проаналізуй:\n\n{transcript}"}],
                },
            )
        data = res.json()
        raw = data["content"][0]["text"]
        clean = raw.strip().lstrip("```json").rstrip("```").strip()
        report = json.loads(clean)

        conv = (
            db.query(Conversation)
            .filter(Conversation.channel == channel, Conversation.external_id == external_id)
            .first()
        )
        if conv:
            conv.quality_score = report.get("score")
            conv.quality_report = json.dumps(report, ensure_ascii=False)
            db.commit()

        return report
    except Exception as e:
        return {"error": str(e)}
