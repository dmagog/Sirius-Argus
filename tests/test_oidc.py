"""pytest-bdd: реальный OIDC-флоу Keycloak (CRED-01). Скип, если Keycloak не поднят."""
import os

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
TOKEN_URL = f"{BASE}/auth/realms/sirius/protocol/openid-connect/token"
scenarios("oidc.feature")

S = {}


@given("получен OIDC-токен Keycloak для роли DS")
def get_token():
    try:
        r = httpx.post(TOKEN_URL, data={
            "client_id": "sirius", "username": "ds", "password": "ds", "grant_type": "password",
        }, timeout=10)
    except Exception as e:  # Keycloak не поднят
        pytest.skip(f"Keycloak недоступен: {e}")
    if r.status_code != 200:
        pytest.skip(f"Keycloak/realm не готов ({r.status_code})")
    S["token"] = r.json()["access_token"]


@when("я зову whoami с этим токеном")
def call_valid():
    S["resp"] = httpx.get(f"{BASE}/api/whoami", headers={"Authorization": f"Bearer {S['token']}"}, timeout=10)


@then("ответ 200 и роль DS")
def ok_ds():
    assert S["resp"].status_code == 200, S["resp"].text
    assert "DS" in S["resp"].json().get("roles", [])


@when("я порчу токен и зову whoami")
def call_tampered():
    bad = S["token"][:-3] + "xxx"
    S["resp"] = httpx.get(f"{BASE}/api/whoami", headers={"Authorization": f"Bearer {bad}"}, timeout=10)


@then("ответ 401 на подделанный токен")
def unauthorized():
    assert S["resp"].status_code == 401, S["resp"].text
