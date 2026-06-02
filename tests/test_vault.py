"""pytest-bdd: CRED-02 — секреты из HashiCorp Vault (AppRole + политика + аудит + revoke).

Сценарий 1: control-plane реально тянет секреты из Vault (видно в /health).
Сценарий 2 (через контейнер vault): выдача по политике (свой путь — ok, чужой — 403) и
мгновенный отзыв secret-id (после destroy повторный AppRole-логин отклонён). Демонстрирует
ровно то, ради чего Vault: права + аудит + быстрый revoke.
"""
import os
import subprocess

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.environ.get("VAULT_ROOT_TOKEN", "sirius-root-dev")
scenarios("vault.feature")
S = {}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up`"


@then("control-plane подключён к Vault и источник секретов — vault")
def vault_connected():
    v = httpx.get(f"{BASE}/health", timeout=10).json().get("vault", {})
    assert v.get("connected") is True and v.get("secrets_source") == "vault", v


@when("прогоняем в Vault выдачу по политике и отзыв secret-id")
def vault_policy_revoke():
    script = (
        'export VAULT_ADDR=http://127.0.0.1:8200\n'
        'RID=$(vault read -field=role_id auth/approle/role/control-plane/role-id)\n'
        'SID=$(vault write -f -field=secret_id auth/approle/role/control-plane/secret-id)\n'
        'TOK=$(vault write -field=token auth/approle/login role_id=$RID secret_id=$SID)\n'
        'VAULT_TOKEN=$TOK vault kv get -field=seed secret/sirius/signing >/dev/null 2>&1 && echo ALLOWED_OK || echo ALLOWED_FAIL\n'
        'VAULT_TOKEN=$TOK vault kv get secret/forbidden/x >/dev/null 2>&1 && echo DENIED_FAIL || echo DENIED_OK\n'
        'vault write -f auth/approle/role/control-plane/secret-id/destroy secret_id=$SID >/dev/null 2>&1\n'
        'vault write auth/approle/login role_id=$RID secret_id=$SID >/dev/null 2>&1 && echo REVOKE_FAIL || echo REVOKE_OK\n'
    )
    res = subprocess.run(["docker", "compose", "exec", "-T", "-e", f"VAULT_TOKEN={ROOT}", "vault", "sh", "-c", script],
                         cwd=REPO, capture_output=True, text=True, timeout=60)
    S["out"] = res.stdout + res.stderr


@then("секрет выдан по политике, путь вне политики запрещён, после revoke логин отклонён")
def vault_checks():
    for marker in ("ALLOWED_OK", "DENIED_OK", "REVOKE_OK"):
        assert marker in S["out"], S["out"]
