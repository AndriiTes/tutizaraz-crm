from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text
from sqlalchemy.sql import func

from .database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    # Звідки прийшло звернення: website / telegram / viber / whatsapp / instagram / phone
    source = Column(String, default="website", index=True)

    # Статус обробки: new / confirmed / cooking / delivering / done / cancelled
    status = Column(String, default="new", index=True)

    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    comment = Column(Text, nullable=True)

    # Ідентифікатор клієнта в каналі: chat_id у Telegram, user_id у Viber,
    # wa_id у WhatsApp тощо. Знадобиться, щоб надсилати відповіді клієнту.
    external_id = Column(String, nullable=True, index=True)

    items = Column(JSON, nullable=True)
    total = Column(Float, default=0)

    # Повне "сире" тіло вебхука — корисно для діагностики, якщо з каналу прийде
    # щось несподіване і його треба буде розібрати вручну
    raw_payload = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Message(Base):
    """
    Окремий журнал листування (на відміну від Order, який представляє
    структуроване замовлення). Кожен вхідний чи вихідний рядок переписки
    зберігається тут. Розмова групується за парою (channel, external_id):
    chat_id у Telegram, session_id у віджеті сайту, user_id у Viber тощо.
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String, index=True)  # telegram / viber / whatsapp / instagram / website-chat
    external_id = Column(String, index=True)
    customer_name = Column(String, nullable=True)
    direction = Column(String)  # "in" (від клієнта) або "out" (від оператора/бота)
    body = Column(Text)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
