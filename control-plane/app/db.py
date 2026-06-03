"""БД control-plane: метаданные + append-only аудит с hash-chain.

SQLite-фоллбэк позволяет гонять каркас и тесты без Postgres; в compose — Postgres.
"""
import logging
import os
from sqlalchemy import create_engine, inspect as sa_inspect, text, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger("sirius.db")

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


# LOG-02: append-only на уровне БД. Аудит можно только дописывать — UPDATE/DELETE
# отбивается триггером (а не логикой приложения). Скомпрометированный control-plane
# не перепишет hash-chain обычным DML. Чтобы тронуть запись, нужен привилегированный
# DDL (отключить триггер) — отдельное заметное действие; в проде app должен ходить
# под non-owner ролью (выдаётся Vault), которой DDL на audit_events недоступен.
_PG_GUARD = (
    """
    CREATE OR REPLACE FUNCTION sirius_audit_no_mutate() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_events is append-only (LOG-02): % rejected', TG_OP;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS sirius_audit_append_only ON audit_events",
    """
    CREATE TRIGGER sirius_audit_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION sirius_audit_no_mutate()
    """,
)
_SQLITE_GUARD = (
    "CREATE TRIGGER IF NOT EXISTS sirius_audit_no_update BEFORE UPDATE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only (LOG-02)'); END",
    "CREATE TRIGGER IF NOT EXISTS sirius_audit_no_delete BEFORE DELETE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only (LOG-02)'); END",
)


def _install_append_only_guard():
    """Ставит append-only-триггер на audit_events. Fail-soft: если не вышло — пишем warning,
    hash-chain (MON-04) всё равно ловит подмену; контроль prevent деградирует до detect."""
    dialect = engine.dialect.name
    stmts = _PG_GUARD if dialect == "postgresql" else _SQLITE_GUARD if dialect == "sqlite" else ()
    if not stmts:
        return
    try:
        with engine.begin() as conn:
            for st in stmts:
                conn.execute(text(st))
        logger.info("append-only guard на audit_events установлен (%s)", dialect)
    except Exception as e:  # noqa: BLE001 — не валим старт из-за усиления, остаётся detect
        logger.warning("append-only guard не установлен (%s): %s", dialect, e)


# Лёгкие аддитивные миграции: create_all НЕ добавляет новые колонки в уже существующие
# таблицы. Для развёрнутых БД (sqlite/postgres) идемпотентно дотягиваем недостающие колонки,
# чтобы не требовать пересоздания тома. Только ADD COLUMN с DEFAULT — безопасно и обратимо.
_ADD_COLUMNS = (
    ("approvals", "decision", "ALTER TABLE approvals ADD COLUMN decision VARCHAR(16) DEFAULT 'approve'"),
    ("findings", "role", "ALTER TABLE findings ADD COLUMN role VARCHAR(32) DEFAULT ''"),
    ("model_versions", "created_at", "ALTER TABLE model_versions ADD COLUMN created_at VARCHAR(32) DEFAULT ''"),
    ("model_versions", "promoted_at", "ALTER TABLE model_versions ADD COLUMN promoted_at VARCHAR(32) DEFAULT ''"),
    ("model_versions", "retired_at", "ALTER TABLE model_versions ADD COLUMN retired_at VARCHAR(32) DEFAULT ''"),
)


def _ensure_columns():
    try:
        insp = sa_inspect(engine)
        tables = set(insp.get_table_names())
    except Exception as e:  # noqa: BLE001
        logger.warning("inspect недоступен, пропускаю миграции колонок: %s", e)
        return
    for table, col, ddl in _ADD_COLUMNS:
        if table not in tables:
            continue  # create_all уже создаст таблицу с актуальной схемой
        if col in {c["name"] for c in insp.get_columns(table)}:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(ddl))
            logger.info("миграция: добавлена колонка %s.%s", table, col)
        except Exception as e:  # noqa: BLE001 — не валим старт из-за миграции
            logger.warning("не удалось добавить колонку %s.%s: %s", table, col, e)


def init_db():
    from . import domain  # noqa: F401 — регистрирует доменные модели на Base
    Base.metadata.create_all(engine)
    _ensure_columns()
    _install_append_only_guard()
