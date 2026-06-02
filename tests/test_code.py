"""pytest-bdd: CODE-01 — ML-aware SAST на код. Код НЕ исполняется (только ast.parse)."""
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("code.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("DS отправляет на скан код с os.system")
def scan_bad():
    code = "import os\ndef train():\n    os.system('echo hi')\n"
    S["resp"] = httpx.post(f"{BASE}/api/scan/code", headers=tok("DS"), content=code.encode(), timeout=10)


@when("DS отправляет на скан безопасный код")
def scan_good():
    code = "def add(a, b):\n    return a + b\n"
    S["resp"] = httpx.post(f"{BASE}/api/scan/code", headers=tok("DS"), content=code.encode(), timeout=10)


@then("скан помечает код небезопасным")
def flagged():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json()["clean"] is False, S["resp"].text


@then("создаётся сработка insecure-code")
def finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "insecure-code" and f["asset"].startswith("code/")
               for f in r.json()["findings"]), r.text


@then("скан помечает код чистым")
def clean():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json()["clean"] is True, S["resp"].text


@when("DS отправляет на скан код с захардкоженным секретом")
def scan_secret():
    code = b'def connect():\n    password = "demoSecret123"\n    return password\n'
    S["resp"] = httpx.post(f"{BASE}/api/scan/code", headers=tok("DS"), content=code, timeout=10)


@then("создаётся сработка secret-exposed")
def secret_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "secret-exposed" for f in r.json()["findings"]), r.text


@when("DS отправляет на скан код с захардкоженным порогом")
def scan_hardcoded():
    code = b"def approve(score):\n    if score > 0.75:\n        return True\n    return False\n"
    S["resp"] = httpx.post(f"{BASE}/api/scan/code", headers=tok("DS"), content=code, timeout=10)


@then("создаётся сработка hardcoded-logic")
def hardcoded_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "hardcoded-logic" for f in r.json()["findings"]), r.text
