"""pytest-bdd: VIS-03 — HITL-гейт промоушена критичной модели."""
import os

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("governance.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("воспроизводимая критичная модель")
def critical_model():
    dv = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                    json={"name": "d", "sensitivity": "open", "source": "internal://curated/d"}, timeout=10).json()["dataset_version_id"]
    m = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "credit", "type": "boosting", "criticality": "financial"}, timeout=10).json()["model_id"]
    v = httpx.post(f"{BASE}/api/models/{m}/versions", headers=tok("DS"),
                   json={"dataset_version_id": dv, "code_commit": "abc123", "env_lock": "req.lock"}, timeout=10).json()["version"]
    S.update(model_id=m, ver=v)


@when("MLSecOps промоутит её без аппрува")
def promote_no_approval():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/promote", headers=tok("MLSecOps"), timeout=10)


@when("MLSecOps аппрувит версию")
def approve():
    r = httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/approve", headers=tok("MLSecOps"),
                   json={"reason": "ревью пройдено"}, timeout=10)
    assert r.status_code == 200, r.text


@when("MLSecOps промоутит её снова")
def promote_again():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/promote", headers=tok("MLSecOps"), timeout=10)


@then(parsers.parse("промоушен заблокирован со статусом {code:d}"))
def blocked(code):
    assert S["resp"].status_code == code, S["resp"].text


@then(parsers.parse("промоушен прошёл со статусом {code:d}"))
def passed(code):
    assert S["resp"].status_code == code, S["resp"].text
