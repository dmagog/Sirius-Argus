"""pytest-bdd: CI-01 — control-plane как CI (security-гейт на коммит + HMAC-вебхук)."""
import hashlib
import hmac
import os

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("ci.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


def _ci_secret():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        for line in open(os.path.join(repo, ".env")):
            if line.startswith("CI_WEBHOOK_SECRET="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return "change-me-ci-webhook"


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


@when("один и тот же подписанный вебхук приходит дважды")
def replayed_webhook():
    # уникальное тело на каждый прогон, чтобы nonce не пересекался между запусками сьюта
    body = b'{"after": "replaytest-' + os.urandom(4).hex().encode() + b'", "repository": {"full_name": "x/y"}}'
    sig = hmac.new(_ci_secret().encode(), body, hashlib.sha256).hexdigest()
    hdr = {"X-Gitea-Signature": sig, "X-Gitea-Delivery": "deliv-" + os.urandom(4).hex()}
    S["first"] = httpx.post(f"{BASE}/api/ci/webhook", headers=hdr, content=body, timeout=60)
    S["second"] = httpx.post(f"{BASE}/api/ci/webhook", headers=hdr, content=body, timeout=60)


@then(parsers.parse("первый принят, а повтор отклонён со статусом {code:d}"))
def replay_rejected(code):
    assert S["first"].status_code != 401, f"первый (валидный) вебхук не должен быть 401: {S['first'].text}"
    assert S["second"].status_code == code, f"повтор должен быть {code}: {S['second'].status_code} {S['second'].text}"
