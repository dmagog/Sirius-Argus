"""pytest-bdd: CRED-03 — Keycloak brute-force protection (временная блокировка аккаунта).

Из ревью (Камиль): у Keycloak не была включена защита от брутфорса. Здесь по выделенному
аккаунту bruteme гоняем серию неверных паролей и проверяем, что после этого даже верный
пароль отклоняется (аккаунт временно заблокирован). Скип, если Keycloak не поднят.
"""
import os

import httpx
import pytest
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
TOKEN_URL = f"{BASE}/auth/realms/sirius/protocol/openid-connect/token"
scenarios("bruteforce.feature")
S = {}


def _login(user, password):
    return httpx.post(TOKEN_URL, data={"client_id": "sirius", "username": user,
                                       "password": password, "grant_type": "password"}, timeout=10)


@given("Keycloak с включённой защитой от брутфорса")
def kc_ready():
    try:
        r = _login("bruteme", "brutepass")
    except Exception as e:  # Keycloak не поднят
        pytest.skip(f"Keycloak недоступен: {e}")
    if r.status_code not in (200, 401):
        pytest.skip(f"Keycloak/realm не готов ({r.status_code})")


@when("по аккаунту идёт серия неверных паролей")
def brute_force():
    for _ in range(7):  # failureFactor=5 → к 6-7 попытке аккаунт временно блокируется
        _login("bruteme", "wrong-" + os.urandom(2).hex())
    S["good"] = _login("bruteme", "brutepass")


@then("аккаунт временно заблокирован — даже верный пароль отклоняется")
def locked_out():
    assert S["good"].status_code != 200, \
        f"ожидали блокировку после серии неверных входов, но верный пароль прошёл ({S['good'].status_code})"
