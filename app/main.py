from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import models
from .database import engine, run_simple_migrations
from .routers import login, orders, webhooks

models.Base.metadata.create_all(bind=engine)
run_simple_migrations()

app = FastAPI(title="Тут&Зараз CRM API")

# TODO: коли сайт matиме постійний домен — звузити allow_origins
# до конкретної адреси замість "*" (зараз дозволено все, щоб
# не блокувати тестування з тимчасових *.pages.dev / *.workers.dev адрес).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhooks.router, tags=["webhooks"])
app.include_router(orders.router, tags=["orders"])
app.include_router(login.router, tags=["auth"])


@app.get("/health")
def health():
    return {"status": "ok"}


# CRM-панель (статичні файли) — віддається з того ж сервісу на тому ж домені,
# що й API, тому ніякого окремого хостингу для адмінки не потрібно.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
