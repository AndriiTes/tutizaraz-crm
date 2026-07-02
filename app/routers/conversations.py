import json
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..ai_agent import run_quality_check
from ..auth import require_auth
from ..database import get_db
from .webhooks import save_message, send_channel_reply

router = APIRouter()


def get_or_create_conv(db: Session, channel: str, external_id: str, customer_name: Optional[str] = None):
    conv = (
        db.query(models.Conversation)
        .filter(models.Conversation.channel == channel, models.Conversation.external_id == external_id)
        .first()
    )
    if not conv:
        conv = models.Conversation(
            channel=channel, external_id=external_id,
            customer_name=customer_name, status="ai", ai_enabled=True
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
    elif customer_name and not conv.customer_name:
        conv.customer_name = customer_name
        db.commit()
    return conv


@router.get("/api/conversations", response_model=List[schemas.ConversationOut])
def list_conversations(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
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

    result = []
    for m in rows:
        conv = (
            db.query(models.Conversation)
            .filter(
                models.Conversation.channel == m.channel,
                models.Conversation.external_id == m.external_id,
            )
            .first()
        )
        conv_status = conv.status if conv else "ai"
        conv_score = conv.quality_score if conv else None
        if status and conv_status != status:
            continue
        result.append(schemas.ConversationOut(
            channel=m.channel,
            external_id=m.external_id,
            customer_name=m.customer_name,
            last_message=m.body,
            last_at=m.created_at,
            unread=(m.direction == "in"),
            status=conv_status,
            quality_score=conv_score,
        ))
    return result


@router.get("/api/conversations/{channel}/{external_id}", response_model=List[schemas.MessageOut])
def get_conversation(
    channel: str, external_id: str,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    rows = (
        db.query(models.Message)
        .filter(models.Message.channel == channel, models.Message.external_id == external_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Розмову не знайдено")
    return rows


@router.get("/api/conversations/{channel}/{external_id}/state", response_model=schemas.ConversationStateOut)
def get_conversation_state(
    channel: str, external_id: str,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    conv = get_or_create_conv(db, channel, external_id)
    return conv


@router.post("/api/conversations/{channel}/{external_id}/reply", response_model=schemas.MessageOut)
async def reply_to_conversation(
    channel: str, external_id: str,
    data: schemas.ReplyIn,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    ok = await send_channel_reply(channel, external_id, data.text)
    if not ok and channel != "website-chat":
        raise HTTPException(status_code=502, detail="Не вдалось надіслати в канал")

    existing = (
        db.query(models.Message)
        .filter(models.Message.channel == channel, models.Message.external_id == external_id)
        .order_by(models.Message.created_at.desc())
        .first()
    )
    customer_name = existing.customer_name if existing else None
    msg = save_message(db, channel=channel, external_id=external_id,
                       customer_name=customer_name, direction="out",
                       body=data.text, sender="human")
    return msg


@router.post("/api/conversations/{channel}/{external_id}/escalate")
async def escalate_conversation(
    channel: str, external_id: str,
    data: schemas.EscalateIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    conv = get_or_create_conv(db, channel, external_id)
    prev_status = conv.status
    conv.status = data.to
    if data.to in ("human", "sales"):
        conv.ai_enabled = False
    db.commit()

    note_text = {
        "human": "Розмову передано людині-оператору.",
        "sales": "Розмову передано у відділ продажів.",
        "done": "Розмову завершено.",
    }.get(data.to, f"Статус змінено на {data.to}.")
    if data.note:
        note_text += f" Примітка: {data.note}"
    save_message(db, channel=channel, external_id=external_id,
                 customer_name=conv.customer_name, direction="out",
                 body=f"[Система] {note_text}", sender="system")

    if data.to == "done" and prev_status != "done":
        background_tasks.add_task(run_quality_check, db, channel, external_id)

    return {"ok": True, "status": conv.status}


@router.post("/api/conversations/{channel}/{external_id}/toggle-ai")
def toggle_ai(
    channel: str, external_id: str,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    conv = get_or_create_conv(db, channel, external_id)
    conv.ai_enabled = not conv.ai_enabled
    db.commit()
    return {"ok": True, "ai_enabled": conv.ai_enabled}


@router.get("/api/conversations/{channel}/{external_id}/quality")
def get_quality_report(
    channel: str, external_id: str,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    conv = (
        db.query(models.Conversation)
        .filter(models.Conversation.channel == channel, models.Conversation.external_id == external_id)
        .first()
    )
    if not conv or not conv.quality_report:
        raise HTTPException(status_code=404, detail="Звіт ще не готовий")
    return json.loads(conv.quality_report)


@router.get("/api/reports/quality")
def list_quality_reports(
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    convs = (
        db.query(models.Conversation)
        .filter(models.Conversation.quality_report.isnot(None))
        .order_by(models.Conversation.updated_at.desc())
        .all()
    )
    result = []
    for c in convs:
        try:
            report = json.loads(c.quality_report)
        except Exception:
            report = {}
        result.append({
            "channel": c.channel,
            "external_id": c.external_id,
            "customer_name": c.customer_name,
            "score": c.quality_score,
            "summary": report.get("summary", ""),
            "strengths": report.get("strengths", []),
            "improvements": report.get("improvements", []),
            "operator_feedback": report.get("operator_feedback", ""),
        })
    return result


@router.get("/public/website-chat/{session_id}/messages")
async def public_widget_messages(session_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Message)
        .filter(models.Message.channel == "website-chat", models.Message.external_id == session_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    return [
        {"id": m.id, "direction": m.direction, "body": m.body,
         "created_at": m.created_at.isoformat()}
        for m in rows
    ]
