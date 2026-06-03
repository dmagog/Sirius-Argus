"""pytest-bdd: MON-05 — непрерывная ре-верификация подписи/целостности прод-моделей.

Из ревью (Михаил): подпись проверяется при промоушене (admission), но не для модели,
УЖЕ стоящей в проде — прод тоже уязвим к подмене. Здесь: подписанную критичную версию
промоутят, затем имитируют подмену уже-прод артефакта (ломаем зарегистрированный hash,
из-за чего подпись перестаёт сходиться) и прогоняют сервер-сайд ре-верификацию прода.
"""
import os
import subprocess

import httpx
from pytest_bdd import given, scenarios, then, when

BASE = os.environ.get("SIRIUS_BASE_URL", "http://localhost:8080")
scenarios("prod_verify.feature")
S = {}


def tok(role):
    return {"Authorization": f"Bearer dev:{role.lower()}:{role}"}


def _psql(sql):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "sirius", "-d", "sirius", "-tAc", sql],
        cwd=repo, capture_output=True, text=True, timeout=20)
    return out.stdout.strip()


@given("подписанная критичная модель в проде")
def signed_critical_in_prod():
    dv = httpx.post(f"{BASE}/api/datasets", headers=tok("DE"),
                    json={"name": "pv", "sensitivity": "open", "source": "internal://curated/pv"},
                    timeout=10).json()["dataset_version_id"]
    m = httpx.post(f"{BASE}/api/models", headers=tok("DS"),
                   json={"name": "pv", "type": "boosting", "criticality": "financial"},
                   timeout=10).json()["model_id"]
    v = httpx.post(f"{BASE}/api/models/{m}/versions", headers=tok("DS"),
                   json={"dataset_version_id": dv, "code_commit": "abc123", "env_lock": "req.lock",
                         "intended_use": "прогноз риска", "limitations": "не финсовет"},
                   timeout=10).json()["version"]
    assert httpx.post(f"{BASE}/api/models/{m}/versions/{v}/sign", headers=tok("MLSecOps"), timeout=10).status_code == 200
    assert httpx.post(f"{BASE}/api/models/{m}/versions/{v}/approve",
                      headers={"Authorization": "Bearer dev:reviewer:MLSecOps"},
                      json={"reason": "ревью пройдено"}, timeout=10).status_code == 200
    assert httpx.post(f"{BASE}/api/models/{m}/versions/{v}/promote", headers=tok("MLSecOps"), timeout=10).status_code == 200
    S.update(m=m, v=v)


@when("артефакт прод-версии подменяют и запускают прод-ре-верификацию")
def tamper_and_verify():
    # имитируем подмену уже-прод артефакта: ломаем зарегистрированный hash — подпись перестаёт сходиться.
    # (audit_events защищён append-only-триггером, а model_versions — нет, так что UPDATE проходит.)
    _psql(f"UPDATE model_versions SET artifact_hash='deadbeefdeadbeefdeadbeefdeadbeef' "
          f"WHERE model_id={S['m']} AND version={S['v']}")
    S["resp"] = httpx.post(f"{BASE}/api/prod/verify-signatures", headers=tok("MLSecOps"), timeout=30).json()


@then("ре-верификация помечает версию как подменённую")
def flagged():
    t = S["resp"].get("tampered", [])
    assert any(x["model_id"] == S["m"] and x["version"] == S["v"] for x in t), S["resp"]


@then("появляется critical-сработка prod-artifact-tampered")
def prod_tamper_finding():
    r = httpx.get(f"{BASE}/api/findings", headers=tok("MLSecOps"), timeout=10)
    assert any(f["verdict"] == "prod-artifact-tampered" and f["asset"] == f"model/{S['m']}/v{S['v']}"
               and f["severity"] == "critical" for f in r.json()["findings"]), r.text
