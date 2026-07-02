from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .models import Base
from .database import engine, run_simple_migrations
from .routers import conversations, login, orders, publish, webhooks

Base.metadata.create_all(bind=engine)
run_simple_migrations()

app = FastAPI(title="Тут&Зараз CRM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks.router, tags=["webhooks"])
app.include_router(orders.router, tags=["orders"])
app.include_router(conversations.router, tags=["conversations"])
app.include_router(publish.router, tags=["publications"])
app.include_router(login.router, tags=["auth"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/ai-status")
def ai_status():
    """Перевіряє який AI-провайдер активний — без виклику зовнішніх API."""
    import os
    if os.getenv("ANTHROPIC_API_KEY"):
        return {"provider": "anthropic", "provider_label": "Claude (Anthropic)"}
    elif os.getenv("GROQ_API_KEY"):
        return {"provider": "groq", "provider_label": "Llama 3.3 (Groq)"}
    return {"provider": "none", "provider_label": "не налаштовано"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
