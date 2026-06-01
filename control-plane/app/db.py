"""БД control-plane: метаданные + append-only аудит с hash-chain.

SQLite-фоллбэк позволяет гонять каркас и тесты без Postgres; в compose — Postgres.
"""
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./sirius.db")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
Base = declarative_base()


class AuditEvent(Base):
    """Append-only событие аудита. Целостность — через hash-chain (см. audit.py)."""
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    ts = Column(String(40), nullable=False)            # ISO-8601 (UTC), фиксируется при записи
    actor = Column(String(255), nullable=False)
    action = Column(String(255), nullable=False)
    obj = Column(String(512), default="")
    was_authorized = Column(Boolean, default=True)
    prev_hash = Column(String(64), default="")
    hash = Column(String(64), nullable=False)


def init_db():
    from . import domain  # noqa: F401 — регистрирует доменные модели на Base
    Base.metadata.create_all(engine)
