"""pytest-bdd: SUP-03 — скан зависимостей (известные CVE не проходят гейт)."""
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("deps.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("DS отправляет на скан requirements с уязвимой зависимостью")
def scan_vuln():
    reqs = b"numpy==1.26.4\nrequests==2.19.0\n"
    S["resp"] = httpx.post(f"{BASE}/api/scan/deps", headers=tok("DS"), content=reqs, timeout=10)


@when("DS отправляет на скан чистые requirements")
def scan_clean():
    reqs = b"numpy==1.26.4\nfastapi==0.115.6\n"
    S["resp"] = httpx.post(f"{BASE}/api/scan/deps", headers=tok("DS"), content=reqs, timeout=10)


@then("скан помечает зависимости небезопасными")
def deps_bad():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json()["clean"] is False, S["resp"].text


@then("создаётся сработка vulnerable-dependency")
def dep_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "vulnerable-dependency" for f in r.json()["findings"]), r.text


@when("сканируются собственные requirements платформы")
def scan_self():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo, "control-plane", "requirements.txt"), "rb") as f:
        reqs = f.read()
    S["resp"] = httpx.post(f"{BASE}/api/scan/deps", headers=tok("MLSecOps"), content=reqs, timeout=10)


@then("скан помечает зависимости чистыми")
def deps_clean():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json()["clean"] is True, S["resp"].text
