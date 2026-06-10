"""Шина событий (Redis Streams). Best-effort: аудит — источник правды, шина — для
наблюдаемости и корреляции (ADR-0008/0009). Доступ к Redis под паролем (AUTH) —
анонимная инъекция событий невозможна (EVT-01).

Здесь же — общие счётчики для rate-limit/детекта в Redis (sliding window + дедуп):
состояние общее для всех воркеров, поэтому лимит нельзя обойти, размазав запросы по
соединениям/процессам (в отличие от in-memory per-worker). Fail-soft: если Redis недоступен,
хелперы возвращают None и вызывающий падает на in-memory-фолбэк.
"""
import os
import secrets

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
        # служебный "type" не перетираем payload'ом; значения ограничиваем по длине
        fields = {"type": str(event_type)}
        fields.update({str(k): str(v)[:512] for k, v in payload.items() if k != "type"})
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


def rate_hit(key: str, window_s: float, now_ts: float):
    """Скользящее окно в Redis (sorted set): дописывает хит, выкидывает старше окна,
    возвращает число хитов в окне. Общий счётчик для всех воркеров. None — Redis недоступен."""
    c = _conn()
    if not c:
        return None
    try:
        member = f"{now_ts:.6f}:{secrets.token_hex(4)}"  # уникальный член на каждый хит
        pipe = c.pipeline()
        pipe.zremrangebyscore(key, 0, now_ts - window_s)
        pipe.zadd(key, {member: now_ts})
        pipe.zcard(key)
        pipe.expire(key, int(window_s) + 1)
        return int(pipe.execute()[2])
    except Exception:
        return None


def once(key: str, ttl_s: float):
    """Дедуп в Redis (SET NX EX): True — впервые за TTL, False — уже было, None — Redis недоступен."""
    c = _conn()
    if not c:
        return None
    try:
        return bool(c.set(key, "1", nx=True, ex=int(ttl_s)))
    except Exception:
        return None


def key_count(key: str) -> int:
    """Сколько хитов сейчас в окне ключа (для проверки/диагностики). 0, если нет/Redis недоступен."""
    c = _conn()
    try:
        return int(c.zcard(key)) if c else 0
    except Exception:
        return 0


def flag(key: str) -> bool:
    """Поставить устойчивый флаг (без TTL) — для durable-состояния, общего всем воркерам
    (напр. отзыв доступа, ACC-03/AUD-12). True — записано, False — Redis недоступен (fail-soft)."""
    c = _conn()
    if not c:
        return False
    try:
        c.set(key, "1")
        return True
    except Exception:
        return False


def flagged(key: str) -> bool:
    """Проверить устойчивый флаг. False, если нет или Redis недоступен (fail-soft)."""
    c = _conn()
    if not c:
        return False
    try:
        return bool(c.exists(key))
    except Exception:
        return False
