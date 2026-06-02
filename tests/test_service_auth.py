"""pytest-bdd: сервис-аккаунт — serving→control-plane по pre-shared токену (рантайм-петля без DEV_AUTH).

Сервис-токен проверяется отдельным путём в auth.get_principal (constant-time, до dev/OIDC и без
оглядки на DEV_AUTH) → роль Service с единственным правом runtime.event. Это и есть прод-режим петли.
"""
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
SVC = os.environ.get("SIRIUS_SERVICE_TOKEN", "svc-serving-local-dev-7f3a9c")
scenarios("service_auth.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up`"


@when("сервис шлёт рантайм-событие со своим токеном")
def svc_event():
    S["resp"] = httpx.post(f"{BASE}/api/runtime/event", headers={"Authorization": f"Bearer {SVC}"},
                           json={"type": "svc-auth-probe", "endpoint": "iris-linear", "client": "svc-test", "count": 1},
                           timeout=10)


@then("событие принято со статусом 200 и создаётся сработка")
def accepted():
    assert S["resp"].status_code == 200, S["resp"].text
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "svc-auth-probe" for f in r.json()["findings"]), r.text


@when("сервис шлёт рантайм-событие с неверным токеном")
def bad_event():
    S["resp"] = httpx.post(f"{BASE}/api/runtime/event", headers={"Authorization": "Bearer svc-WRONG-token"},
                           json={"type": "svc-auth-probe", "endpoint": "x", "client": "y", "count": 1}, timeout=10)


@then("запрос отклонён со статусом 401")
def rejected():
    assert S["resp"].status_code == 401, S["resp"].text
