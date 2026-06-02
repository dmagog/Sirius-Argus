"""pytest-bdd: J — принятие остаточного риска под условиями (GRC exception).

Открытая critical-сработка на версии блокирует промоушен; CEO (отдельно от промоутера-MLSecOps)
принимает риск с обоснованием/условиями/сроком → промоушен проходит как conditional. В аудит.
"""
import hashlib
import os
from datetime import datetime, timedelta, timezone

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("risk.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


@given("поднятый control-plane")
def up():
    assert httpx.get(f"{BASE}/health", timeout=10).status_code == 200, "сначала `make up` (с DEV_AUTH=1)"


@given("воспроизводимая версия с открытой critical-сработкой")
def reproducible_with_critical():
    dv = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                    json={"name": "risk-ds", "source": "internal://curated/risk"}, timeout=10).json()
    mid = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                     json={"name": "risk-model", "criticality": "internal"}, timeout=10).json()["model_id"]
    h = hashlib.sha256(b"orig-artifact-bytes").hexdigest()
    ver = httpx.post(f"{BASE}/api/models/{mid}/versions", headers=tok("DS"),
                     json={"dataset_version_id": dv["dataset_version_id"], "code_commit": "abc123",
                           "env_lock": "req.lock", "artifact_hash": h}, timeout=10).json()["version"]
    # инъекция critical: загружаем НЕ тот артефакт → integrity-violation → Finding(artifact-tampered, critical)
    r = httpx.post(f"{BASE}/api/models/{mid}/versions/{ver}/verify-artifact", headers=tok("MLSecOps"),
                   content=b"TAMPERED-bytes", timeout=10)
    assert r.status_code == 409, r.text
    S["mid"], S["ver"] = mid, ver


@when("MLSecOps промоутит версию")
@when("MLSecOps промоутит версию повторно")
def promote():
    S["resp"] = httpx.post(f"{BASE}/api/models/{S['mid']}/versions/{S['ver']}/promote",
                           headers=tok("MLSecOps"), timeout=10)


@then("промоушен отклонён со статусом 422")
def promote_blocked():
    assert S["resp"].status_code == 422, S["resp"].text


@when("DS пытается принять риск")
def ds_accepts():
    S["resp"] = httpx.post(f"{BASE}/api/risk-acceptance", headers=tok("DS"),
                           json={"ref": f"model/{S['mid']}/v{S['ver']}", "justification": "x"}, timeout=10)


@then("принятие риска отклонено со статусом 403")
def risk_denied():
    assert S["resp"].status_code == 403, S["resp"].text


@when("CEO принимает риск с условиями и сроком")
def ceo_accepts():
    exp = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds")
    r = httpx.post(f"{BASE}/api/risk-acceptance", headers=tok("CEO"),
                   json={"ref": f"model/{S['mid']}/v{S['ver']}", "scope": "version",
                         "justification": "осознанный приём: низкий blast-radius, актив internal",
                         "conditions": "ре-скан и закрытие сработки в течение срока", "expires_at": exp}, timeout=10)
    assert r.status_code == 200, r.text


@then("промоушен проходит как conditional")
def promote_conditional():
    assert S["resp"].status_code == 200, S["resp"].text
    assert S["resp"].json().get("conditional") is True, S["resp"].text
