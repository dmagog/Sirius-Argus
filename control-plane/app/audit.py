"""Tamper-evident аудит: каждое событие связано хешем с предыдущим (hash-chain).

Подмена/удаление записи рвёт цепочку — это и есть сценарий MON-04.
"""
import hashlib
import json
import logging
import threading
from datetime import datetime, timezone

from . import bus
from .db import SessionLocal, AuditEvent

logger = logging.getLogger("sirius.audit")

# hash-chain должен строиться строго последовательно: сериализуем read-prev + insert,
# иначе конкурентные запросы (напр. флуд рантайм-событий) читают один prev_hash и рвут цепочку.
_chain_lock = threading.Lock()


def _digest(prev_hash: str, payload: dict) -> str:
    blob = prev_hash + json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def append_event(actor: str, action: str, obj: str = "", was_authorized: bool = True) -> int:
    ts = datetime.now(timezone.utc).isoformat()
    payload = {"ts": ts, "actor": actor, "action": action, "obj": obj, "was_authorized": was_authorized}
    with _chain_lock:
        with SessionLocal() as s:
            last = s.query(AuditEvent).order_by(AuditEvent.id.desc()).first()
            prev = last.hash if last else ""
            ev = AuditEvent(
                ts=ts, actor=actor, action=action, obj=obj,
                was_authorized=was_authorized, prev_hash=prev, hash=_digest(prev, payload),
            )
            s.add(ev)
            s.commit()
            eid = ev.id
            head = ev.hash
    # внешнее якорение головы цепочки: голову гоним в шину (Redis) и в лог (Loki) — вне Postgres.
    # Даже если кто-то отключит append-only-триггер и перепишет строки с пересчётом хешей, новая
    # голова разойдётся с уже отгруженной наружу историей голов → подмена остаётся обнаружимой.
    bus.publish("audit", {"actor": actor, "action": action, "obj": obj,
                          "authorized": was_authorized, "id": eid, "head": head})
    logger.info("audit id=%s action=%s actor=%s head=%s", eid, action, actor, head[:12])
    return eid


def recent(limit: int = 50):
    with SessionLocal() as s:
        rows = s.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit).all()
        return list(reversed(rows))


def verify_chain() -> bool:
    """Пересчитывает цепочку: True если целостна (для MON-04)."""
    with SessionLocal() as s:
        evs = s.query(AuditEvent).order_by(AuditEvent.id.asc()).all()
    prev = ""
    for e in evs:
        payload = {"ts": e.ts, "actor": e.actor, "action": e.action, "obj": e.obj, "was_authorized": e.was_authorized}
        if e.prev_hash != prev or e.hash != _digest(prev, payload):
            return False
        prev = e.hash
    return True
