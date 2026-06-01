"""pytest-bdd: policy-матрица промоушена критичной модели — GOV-01, SUP-04, VIS-03.

Каждый сценарий выдаёт всё, кроме проверяемого: так изолируется конкретный гейт.
Порядок гейтов в control-plane: MON-02 → GOV-01 → SUP-04 → VIS-03.
"""
import os

import httpx
from pytest_bdd import given, parsers, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("governance.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


def _critical_version(intended_use="прогноз риска дефолта", limitations="не для физлиц; не финсовет",
                      signature="cosign:abc123"):
    dv = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                    json={"name": "d", "sensitivity": "open", "source": "internal://curated/d"}, timeout=10).json()["dataset_version_id"]
    m = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "credit", "type": "boosting", "criticality": "financial"}, timeout=10).json()["model_id"]
    body = {"dataset_version_id": dv, "code_commit": "abc123", "env_lock": "req.lock",
            "intended_use": intended_use, "limitations": limitations, "signature": signature}
    v = httpx.post(f"{BASE}/api/models/{m}/versions", headers=tok("DS"), json=body, timeout=10).json()["version"]
    S.update(model_id=m, ver=v)


@given("критичная версия без модель-карты")
def no_card():
    _critical_version(intended_use="", limitations="")


@given("критичная версия без подписи")
def no_signature():
    _critical_version(signature="")


@given("полная критичная версия (карта и подпись на месте)")
def full_version():
    _critical_version()


def _promote():
    return httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/promote", headers=tok("MLSecOps"), timeout=10)


@when("MLSecOps промоутит критичную версию")
def promote():
    S["resp"] = _promote()


@when("MLSecOps аппрувит версию")
def approve():
    # аппрувит ДРУГОЙ MLSecOps (reviewer), не тот, кто будет промоутить (ACC-02)
    r = httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/approve",
                   headers={"Authorization": "Bearer dev:reviewer:MLSecOps"}, json={"reason": "ревью пройдено"}, timeout=10)
    assert r.status_code == 200, r.text


@when("MLSecOps сам аппрувит и сам промоутит")
def self_approve_then_promote():
    httpx.post(f"{BASE}/api/models/{S['model_id']}/versions/{S['ver']}/approve", headers=tok("MLSecOps"),
               json={"reason": "самоаппрув"}, timeout=10)
    S["resp"] = _promote()


@given("воспроизводимая версия выведена из эксплуатации")
def retired_version():
    dv = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                    json={"name": "d", "sensitivity": "open", "source": "internal://curated/d"}, timeout=10).json()["dataset_version_id"]
    m = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "m", "type": "boosting", "criticality": "internal"}, timeout=10).json()["model_id"]
    v = httpx.post(f"{BASE}/api/models/{m}/versions", headers=tok("DS"),
                   json={"dataset_version_id": dv, "code_commit": "abc123", "env_lock": "req.lock"}, timeout=10).json()["version"]
    assert httpx.post(f"{BASE}/api/models/{m}/versions/{v}/promote", headers=tok("MLSecOps"), timeout=10).status_code == 200
    assert httpx.post(f"{BASE}/api/models/{m}/versions/{v}/retire", headers=tok("MLSecOps"), timeout=10).status_code == 200
    S.update(model_id=m, ver=v)


@when("MLSecOps промоутит изъятую версию")
def promote_retired():
    S["resp"] = _promote()


@when("MLSecOps промоутит её снова")
def promote_again():
    S["resp"] = _promote()


@then(parsers.parse("промоушен заблокирован со статусом {code:d}"))
def blocked(code):
    assert S["resp"].status_code == code, S["resp"].text


@then(parsers.parse("промоушен прошёл со статусом {code:d}"))
def passed(code):
    assert S["resp"].status_code == code, S["resp"].text
