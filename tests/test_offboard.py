"""pytest-bdd: ACC-03 — offboarding немедленно отзывает доступ субъекта."""
import os

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("offboard.feature")
S = {}
_ACTOR = "ex-employee-9f3"  # одноразовый субъект, чтобы не отзывать рабочих ds/de/mlsecops


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("MLSecOps выводит сотрудника из системы")
def do_offboard():
    r = httpx.post(f"{BASE}/api/offboard", headers={"Authorization": "Bearer dev:mlsecops:MLSecOps"},
                   json={"actor": _ACTOR}, timeout=10)
    assert r.status_code == 200, r.text


@when("отозванный сотрудник делает запрос")
def revoked_request():
    S["resp"] = httpx.get(f"{BASE}/api/whoami", headers={"Authorization": f"Bearer dev:{_ACTOR}:DS"}, timeout=10)


@then(parsers.parse("запрос отклонён со статусом {code:d}"))
def rejected(code):
    assert S["resp"].status_code == code, S["resp"].text
