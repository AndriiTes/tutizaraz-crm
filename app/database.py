import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# DATABASE_URL береться зі змінних середовища на Render.
# Локально (для тестів без бази) використовується SQLite-файл.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./local.db")

# Neon/Render інколи видають URL у форматі postgres://, SQLAlchemy 2.x хоче postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_simple_migrations():
    """
    Легка авто-міграція без Alembic: якщо в моделі з'явилось нове поле,
    а в реальній таблиці його ще немає (наприклад, таблицю створили
    раніше, до того як модель оновили) — дописує відсутню колонку.
    Розрахована на маленький проєкт, де схема міняється нечасто.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "orders" not in inspector.get_table_names():
        return  # таблиці ще нема — create_all() створить її одразу з усіма колонками

    existing_columns = {col["name"] for col in inspector.get_columns("orders")}

    from . import models  # локальний імпорт, щоб уникнути циклічної залежності

    with engine.begin() as conn:
        for column in models.Order.__table__.columns:
            if column.name in existing_columns:
                continue
            col_type = column.type.compile(engine.dialect)
            conn.execute(text(f'ALTER TABLE orders ADD COLUMN "{column.name}" {col_type}'))
