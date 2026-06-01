"""pytest-bdd: VIS-01 — карта покрытия + CEO-вью на live-данных."""
import os
import pickle

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("visibility.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


class _Evil:
    def __reduce__(self):
        return (os.system, ("echo sirius-demo-marker",))  # безвреден, не исполняется


@given("есть активность и сработки")
def activity():
    m = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "ext", "type": "boosting", "criticality": "internal"}, timeout=10).json()["model_id"]
    # вредоносный приём → 422 + Finding(malicious) + audit "model.ingest.blocked"
    httpx.post(f"{BASE}/api/models/{m}/ingest", headers=tok("DS"), content=pickle.dumps(_Evil()), timeout=15)


@when("CEO открывает карту покрытия")
def ceo_opens():
    S["resp"] = httpx.get(f"{BASE}/api/coverage", headers=tok("CEO"), timeout=10)


@then("видны контроли с привязкой к угрозам")
def controls_shown():
    assert S["resp"].status_code == 200, S["resp"].text
    j = S["resp"].json()
    assert j["controls"] and all(c.get("threat") and c.get("control") for c in j["controls"]), j


@then("KPI отражают сработки и блокировки")
def kpi_live():
    k = S["resp"].json()["kpi"]
    assert k["findings_total"] >= 1 and k["blocked_attempts"] >= 1 and "coverage" in k, k


@then("CEO-вью отдаётся страницей")
def ceo_html():
    r = httpx.get(f"{BASE}/coverage", timeout=10)
    assert r.status_code == 200 and "Карта покрытия" in r.text, r.text
