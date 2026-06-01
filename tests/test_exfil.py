"""pytest-bdd: EXF-01 — детект инсайдерской массовой выгрузки моделей."""
import os

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("exfil.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@when("актор выгружает модель аномально много раз")
def bulk_export():
    mid = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                     json={"name": "exportable", "type": "boosting", "criticality": "internal"}, timeout=10).json()["model_id"]
    last = None
    for _ in range(20):
        last = httpx.get(f"{BASE}/api/models/{mid}/export", headers=tok("DS"), timeout=10)
    S["last"] = last


@then("выгрузка троттлится со статусом 429")
def throttled():
    assert S["last"].status_code == 429, S["last"].text


@then("появляется сработка bulk-exfiltration по актору")
def exfil_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "bulk-exfiltration" and f["asset"].startswith("actor/")
               for f in r.json()["findings"]), r.text
