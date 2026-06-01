"""Маскирование секретов в логах (LOG-01).

Любая строка лога проходит через фильтр: Bearer-токены и значения вида
password/secret/token=... редактируются. Аудит (Postgres) — отдельный авторитетный
стор; логи — операционные (ADR-0009), и в них секреты не утекают.
"""
import logging
import re

_PATTERNS = [
    (re.compile(r"Bearer\s+\S+"), "Bearer ***"),
    (re.compile(r"(?i)(password|secret|token|apikey|api_key)(\"?\s*[:=]\s*\"?)([^\"',\s]+)"), r"\1\2***"),
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            for pat, repl in _PATTERNS:
                msg = pat.sub(repl, msg)
            record.msg = msg
            record.args = ()
        except Exception:
            pass
        return True


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "sirius"):
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False
