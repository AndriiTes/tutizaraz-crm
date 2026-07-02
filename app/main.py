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


app.mount("/", StaticFiles(directory="static", html=True), name="static")
