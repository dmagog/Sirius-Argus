"""AuthN — OIDC-токены Keycloak, fail-closed.

- Нет токена / невалидный / Keycloak недоступен → 401 (никогда не open-by-default). Это ACC-05 и AUTH-01.
- Object-level authz — отдельно, в эндпоинтах (Keycloak даёт роль, не право на объект).
- DEV_AUTH=1 включает локальные токены `Bearer dev:<user>:<role>` для каркаса/тестов без Keycloak.
"""
import hmac
import os

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

from . import bus

DEV_AUTH = os.environ.get("DEV_AUTH", "0") == "1"
JWKS_URL = os.environ.get("KEYCLOAK_JWKS_URL", "")
# AUD-05: ожидаемые audience/issuer OIDC-токена. Если заданы — токен, выпущенный для другого
# клиента/realm (grafana/gitea/minio), отвергается. Пусто → проверка выключена (dev/тесты, где
# токен берут ROPC-ом у клиента `sirius`). В проде задаём через env (см. .env.production.example).
OIDC_AUDIENCE = os.environ.get("OIDC_AUDIENCE", "")
OIDC_ISSUER = os.environ.get("OIDC_ISSUER", "")
ROLES = {"DS", "DE", "MLSecOps", "Product", "CEO"}
# Сервис-аккаунт (service-to-service): pre-shared токен для serving→control-plane.
# Не human-роль, а системный актор Service с узким правом (runtime.event). Независим от DEV_AUTH.
SERVICE_TOKEN = os.environ.get("SERVICE_TOKEN", "")
SERVICE_SUB = os.environ.get("SERVICE_SUB", "svc:serving")
_REVOKED = set()  # ACC-03: отозванные (offboarded) субъекты — доступ закрывается немедленно
_REVOKE_PREFIX = "sirius:revoked:"  # AUD-12: durable-отзыв в Redis (переживает рестарт, виден всем воркерам)


def revoke(sub: str):
    _REVOKED.add(sub)
    bus.flag(_REVOKE_PREFIX + sub)  # fail-soft: если Redis недоступен — остаётся in-memory


def is_revoked(sub: str) -> bool:
    if sub in _REVOKED:
        return True
    if bus.flagged(_REVOKE_PREFIX + sub):  # durable-источник (другой воркер/после рестарта)
        _REVOKED.add(sub)  # подтянуть в локальный кэш
        return True
    return False


_jwks_client = None


def _jwks():
    global _jwks_client
    if _jwks_client is None and JWKS_URL:
        _jwks_client = PyJWKClient(JWKS_URL)
    return _jwks_client


# Приоритет ролей для выбора одной «основной» (субъект в проде может иметь несколько realm-ролей).
# Порядок: сначала роли контроля/решений, затем разработки, затем системный актор.
_ROLE_PRIORITY = ("MLSecOps", "CEO", "Product", "DE", "DS", "Service")


def primary_role(roles) -> str:
    """Одна «основная» роль из набора ролей субъекта — для записи в Finding.role.
    Делает «кто причастен» точным и в проде (где sub — UUID Keycloak, а не username).
    Пусто, если ни одной известной роли нет (anonymous/системные пути без роли)."""
    rs = set(roles or ())
    for r in _ROLE_PRIORITY:
        if r in rs:
            return r
    return ""


class Principal:
    def __init__(self, sub: str, roles):
        self.sub = sub
        self.roles = set(roles)

    def primary_role(self) -> str:
        return primary_role(self.roles)


def get_principal(authorization: str = Header(default="")) -> "Principal":
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization[len("Bearer "):]

    # Сервис-аккаунт: pre-shared токен (constant-time сравнение), независим от DEV_AUTH и Keycloak.
    # Узкая роль Service — рантайм-петля serving→control-plane работает и в проде (DEV_AUTH=0).
    if SERVICE_TOKEN and hmac.compare_digest(token, SERVICE_TOKEN):
        return Principal(SERVICE_SUB, ["Service"])

    if DEV_AUTH and token.startswith("dev:"):
        parts = token.split(":", 2)
        if len(parts) != 3 or parts[2] not in ROLES:
            raise HTTPException(status_code=401, detail="bad dev token")
        if parts[1] in _REVOKED:
            raise HTTPException(status_code=401, detail="access revoked (offboarded)")
        return Principal(parts[1], [parts[2]])

    client = _jwks()
    if client is None:
        # auth-бэкенд не настроен или недоступен → fail-closed (AUTH-01)
        raise HTTPException(status_code=401, detail="auth backend unavailable")
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        # AUD-05: aud/iss проверяем, только если заданы (иначе — прежнее поведение для dev/тестов)
        opts = {"verify_aud": bool(OIDC_AUDIENCE)}
        kw = {}
        if OIDC_AUDIENCE:
            kw["audience"] = OIDC_AUDIENCE
        if OIDC_ISSUER:
            kw["issuer"] = OIDC_ISSUER
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], options=opts, **kw)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")
    roles = (claims.get("realm_access") or {}).get("roles", [])
    sub = claims.get("sub", "unknown")
    if is_revoked(sub):  # AUD-12: durable-отзыв (Redis), а не только in-memory
        raise HTTPException(status_code=401, detail="access revoked (offboarded)")
    return Principal(sub, [r for r in roles if r in ROLES])
