"""Секреты из HashiCorp Vault (AppRole) с фолбэком на env.

Зачем (рекомендация куратора): секреты выдаются по политике (least privilege), каждый доступ
в аудите Vault, и их можно мгновенно отозвать/ротировать (revoke/rotate лиза/токена). control-plane
аутентифицируется по AppRole (role_id+secret_id из общего тома, не «секрет-зеро» в env) и тянет
signing-ключ и service-token. Если Vault недоступен — fail-soft на env (стек не падает).
Vault в демо — dev-режим (воспроизводимо); в проде — file/raft + auto-unseal (KMS/HSM).
"""
import logging
import os

logger = logging.getLogger("sirius")

_ADDR = os.environ.get("VAULT_ADDR", "")
_ROLE_ID_FILE = os.environ.get("VAULT_ROLE_ID_FILE", "/vault-creds/role_id")
_SECRET_ID_FILE = os.environ.get("VAULT_SECRET_ID_FILE", "/vault-creds/secret_id")
_KV_MOUNT = os.environ.get("VAULT_KV_MOUNT", "secret")
_client = None
_connected = False
_source = "env"  # откуда взяты секреты: vault | env


def connected() -> bool:
    return _connected


def source() -> str:
    return _source


def _login():
    global _client, _connected
    if not _ADDR:
        return None
    try:
        import hvac
        c = hvac.Client(url=_ADDR)
        with open(_ROLE_ID_FILE) as f:
            role_id = f.read().strip()
        with open(_SECRET_ID_FILE) as f:
            secret_id = f.read().strip()
        c.auth.approle.login(role_id=role_id, secret_id=secret_id)
        if c.is_authenticated():
            _client, _connected = c, True
            return c
    except Exception as e:
        logger.warning("Vault AppRole-логин не удался (%s) → фолбэк на env-секреты", e)
    return None


def get(path: str, key: str):
    """Прочитать ключ из KV v2 (path вида 'sirius/signing'). None при ошибке/отсутствии."""
    if _client is None:
        return None
    try:
        r = _client.secrets.kv.v2.read_secret_version(path=path, mount_point=_KV_MOUNT, raise_on_deleted_version=False)
        return (r["data"]["data"] or {}).get(key)
    except Exception as e:
        logger.warning("Vault read %s: %s", path, e)
        return None


def hydrate_env():
    """Подтянуть секреты из Vault в окружение ДО импорта signing/auth. Фолбэк — оставить env как есть."""
    global _source
    if _login() is None:
        return
    seed = get("sirius/signing", "seed")
    if seed:
        os.environ["SIGNING_SEED"] = seed
    svc = get("sirius/service-token", "token")
    if svc:
        os.environ["SERVICE_TOKEN"] = svc
    if seed or svc:
        _source = "vault"
        logger.info("секреты подтянуты из Vault (signing=%s, service-token=%s)", bool(seed), bool(svc))
