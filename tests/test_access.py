"""pytest-bdd: гоняет сценарии против ЖИВОГО стека (через reverse-proxy).

Запуск: подними стек (`make up`), затем `cd tests && pip install -r requirements.txt && pytest`.
BASE по умолчанию http://localhost:8080 (reverse-proxy). Не моки — реальные HTTP-запросы.
"""
import os

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("access.feature")


class Ctx:
    resp = None


ctx = Ctx()


@given("поднятый control-plane")
def control_plane_up():
    r = httpx.get(f"{BASE}/health", timeout=10)
    assert r.status_code == 200, "control-plane недоступен — сначала `make up`"


@when(parsers.parse('я обращаюсь к "{path}" без токена'))
def call_no_token(path):
    ctx.resp = httpx.get(f"{BASE}{path}", timeout=10)


@when(parsers.parse('я обращаюсь к "{path}" с токеном "{token}"'))
def call_with_token(path, token):
    ctx.resp = httpx.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=10)


@then(parsers.parse("ответ {code:d}"))
def check_status(code):
    assert ctx.resp.status_code == code


@then("в аудит-таймлайне есть access.denied")
def audit_has_denied():
    assert "access.denied" in httpx.get(f"{BASE}/ui/audit", timeout=10).text
