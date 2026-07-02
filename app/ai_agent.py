import json
import os
from typing import Optional

import httpx

# Groq — безкоштовна альтернатива з Llama 3.3 70B.
# Якщо задано ANTHROPIC_API_KEY — використовуємо Claude (платно).
# Якщо задано GROQ_API_KEY — використовуємо Groq/Llama (безкоштовно).
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Визначаємо провайдера автоматично
if ANTHROPIC_API_KEY:
    _PROVIDER = "anthropic"
    _MODEL = "claude-sonnet-4-6"
    _API_URL = "https://api.anthropic.com/v1/messages"
elif GROQ_API_KEY:
    _PROVIDER = "groq"
    _MODEL = "llama-3.3-70b-versatile"
    _API_URL = "https://api.groq.com/openai/v1/chat/completions"
else:
    _PROVIDER = "none"
    _MODEL = ""
    _API_URL = ""

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
    if _PROVIDER == "none":
        return {"can_answer": False, "response": "", "reason": "Не задано API ключ (GROQ_API_KEY або ANTHROPIC_API_KEY)"}

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
        if _PROVIDER == "anthropic":
            return await _call_anthropic(messages_payload, AI_OPERATOR_SYSTEM, 500)
        else:
            return await _call_groq(messages_payload, AI_OPERATOR_SYSTEM, 500)
    except Exception as e:
        return {"can_answer": False, "response": "", "reason": str(e)}


async def _call_anthropic(messages: list, system: str, max_tokens: int) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": "claude-sonnet-4-6", "max_tokens": max_tokens,
                  "system": system, "messages": messages},
        )
    data = res.json()
    if "error" in data:
        err = data["error"]
        return {"can_answer": False, "response": "", "reason": f'{err.get("type")}: {err.get("message")}'}
    if "content" not in data or not data["content"]:
        return {"can_answer": False, "response": "", "reason": f"Порожня відповідь (HTTP {res.status_code})"}
    return _parse_json_response(data["content"][0]["text"])


async def _call_groq(messages: list, system: str, max_tokens: int) -> dict:
    # Groq використовує OpenAI-сумісний формат: system передається як перше повідомлення
    full_messages = [{"role": "system", "content": system}] + messages
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": _MODEL, "max_tokens": max_tokens,
                  "messages": full_messages},
        )
    data = res.json()
    if "error" in data:
        err = data["error"]
        return {"can_answer": False, "response": "", "reason": str(err.get("message", err))}
    if "choices" not in data or not data["choices"]:
        return {"can_answer": False, "response": "", "reason": f"Порожня відповідь Groq (HTTP {res.status_code})"}
    return _parse_json_response(data["choices"][0]["message"]["content"])


def _parse_json_response(raw: str) -> dict:
    clean = raw.strip()
    if "```" in clean:
        parts = clean.split("```")
        for part in parts:
            stripped = part.lstrip("json").strip()
            if stripped.startswith("{"):
                clean = stripped
                break
    clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Якщо модель не дотрималась JSON-формату — вважаємо що відповідь є
        return {"can_answer": True, "response": clean, "reason": ""}


async def run_quality_check(db, channel: str, external_id: str) -> dict:
    if _PROVIDER == "none":
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
        user_msg = [{"role": "user", "content": f"Проаналізуй:\n\n{transcript}"}]
        if _PROVIDER == "anthropic":
            report = await _call_anthropic(user_msg, AI_QUALITY_SYSTEM, 800)
        else:
            report = await _call_groq(user_msg, AI_QUALITY_SYSTEM, 800)

        if not isinstance(report, dict) or "score" not in report:
            return report

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
