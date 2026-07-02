import os
from typing import List

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_auth
from ..database import get_db

router = APIRouter()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHANNEL_CHAT_ID", "")


async def _publish_telegram(text: str, image_url: str | None) -> dict:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return {"ok": False, "error": "Telegram не налаштований (TELEGRAM_BOT_TOKEN або TELEGRAM_CHANNEL_CHAT_ID)"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if image_url:
                res = await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                    json={"chat_id": TELEGRAM_CHAT_ID, "photo": image_url, "caption": text},
                )
            else:
                res = await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                )
        data = res.json()
        return {"ok": data.get("ok", False), "error": data.get("description")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/publications", response_model=schemas.PublicationOut)
async def create_publication(
    payload: schemas.PublicationIn,
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    pub = models.Publication(
        channels=payload.channels,
        text=payload.text,
        image_url=payload.image_url,
        status="sending",
    )
    db.add(pub)
    db.commit()
    db.refresh(pub)

    results = {}
    for ch in payload.channels:
        if ch == "telegram":
            results["telegram"] = await _publish_telegram(payload.text, payload.image_url)
        else:
            results[ch] = {"ok": False, "error": f"Канал {ch} ще не підключено"}

    all_ok = all(r.get("ok") for r in results.values())
    pub.results = results
    pub.status = "sent" if all_ok else "partial"
    db.commit()
    db.refresh(pub)
    return pub


@router.get("/api/publications", response_model=List[schemas.PublicationOut])
def list_publications(
    db: Session = Depends(get_db),
    _auth: bool = Depends(require_auth),
):
    return db.query(models.Publication).order_by(models.Publication.created_at.desc()).all()
