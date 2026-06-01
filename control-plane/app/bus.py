"""Шина событий (Redis Streams). Best-effort: аудит — источник правды, шина — для
наблюдаемости и корреляции (ADR-0008/0009). Доступ к Redis под паролем (AUTH) —
анонимная инъекция событий невозможна (EVT-01).
"""
import os

try:
    import redis
except Exception:  # redis может отсутствовать при unit-прогоне
    redis = None

REDIS_URL = os.environ.get("REDIS_URL", "")
STREAM = "sirius.events"
_client = None


def _conn():
    global _client
    if _client is None and REDIS_URL and redis is not None:
        _client = redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    return _client


def publish(event_type: str, payload: dict) -> bool:
    c = _conn()
    if not c:
        return False
    try:
        fields = {"type": event_type, **{k: str(v) for k, v in payload.items()}}
        c.xadd(STREAM, fields, maxlen=10000, approximate=True)
        return True
    except Exception:
        return False  # fail-soft: действие не блокируем, аудит уже записан


def connected() -> bool:
    c = _conn()
    try:
        return bool(c and c.ping())
    except Exception:
        return False


def stream_len() -> int:
    c = _conn()
    try:
        return int(c.xlen(STREAM)) if c else 0
    except Exception:
        return 0
