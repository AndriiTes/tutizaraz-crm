from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Text, Boolean
from sqlalchemy.sql import func

from .database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, default="website", index=True)
    status = Column(String, default="new", index=True)
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    external_id = Column(String, nullable=True, index=True)
    items = Column(JSON, nullable=True)
    total = Column(Float, default=0)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String, index=True)
    external_id = Column(String, index=True)
    customer_name = Column(String, nullable=True)
    direction = Column(String)  # "in" / "out"
    sender = Column(String, default="bot")  # "customer" / "bot" / "ai" / "human" / "sales"
    body = Column(Text)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    """Відслідковує стан кожної розмови (channel + external_id)."""
    __tablename__ = "conversations_state"

    id = Column(Integer, primary_key=True, index=True)
    channel = Column(String, index=True)
    external_id = Column(String, index=True)
    customer_name = Column(String, nullable=True)

    # Статус розмови:
    # "ai"    — обробляє AI-оператор
    # "human" — ескальовано людині-оператору
    # "sales" — ескальовано у відділ продажів
    # "done"  — завершено, чекає контролю якості
    status = Column(String, default="ai", index=True)

    ai_enabled = Column(Boolean, default=True)
    assigned_to = Column(String, nullable=True)  # ім'я / ID оператора

    # Результат контролю якості (заповнюється AI після завершення)
    quality_score = Column(Integer, nullable=True)     # 1-10
    quality_report = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Publication(Base):
    """Пост для публікації в соцмережах."""
    __tablename__ = "publications"

    id = Column(Integer, primary_key=True, index=True)
    channels = Column(JSON)       # ["telegram", "viber", ...]
    text = Column(Text)
    image_url = Column(String, nullable=True)
    status = Column(String, default="draft")  # "draft" / "sent" / "failed"
    results = Column(JSON, nullable=True)     # { channel: { ok, error } }
    created_at = Column(DateTime(timezone=True), server_default=func.now())

