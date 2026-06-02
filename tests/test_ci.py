"""pytest-bdd: CI-01 — control-plane как CI (security-гейт на коммит + HMAC-вебхук)."""
import os

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("ci.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=60).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("на CI-гейт приходит коммит с опасным кодом")
def poisoned():
    S["resp"] = httpx.post(f"{BASE}/api/ci/scan", headers=tok("DE"),
                           json={"ref": "feature/x", "files": [{"path": "train.py", "content": "import os\nos.system('echo hi')\n"}]}, timeout=60)


@when("на CI-гейт приходит чистый коммит")
def clean():
    S["resp"] = httpx.post(f"{BASE}/api/ci/scan", headers=tok("DE"),
                           json={"ref": "feature/x", "files": [{"path": "train.py", "content": "def f(x):\n    return x * 2\n"}]}, timeout=60)


@when("приходит вебхук с неверной подписью")
def forged_webhook():
    S["resp"] = httpx.post(f"{BASE}/api/ci/webhook", headers={"X-Gitea-Signature": "deadbeef"},
                           content=b'{"after": "abc123", "repository": {"full_name": "x/y"}}', timeout=60)


@then("гейт не пройден и есть сработка")
def not_passed():
    assert S["resp"].status_code == 200, S["resp"].text
    j = S["resp"].json()
    assert j["passed"] is False and j["findings"], j


@then("гейт пройден")
def gate_passed():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json()["passed"] is True, S["resp"].text


@then(parsers.parse("вебхук отклонён со статусом {code:d}"))
def webhook_rejected(code):
    assert S["resp"].status_code == code, S["resp"].text
